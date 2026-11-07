"""One-off: generate SYNTHETIC reef images with Nano Banana for fixtures.

Run manually, not per test. Each image costs a real Gemini call. Outputs go to
eval/fixtures/synthetic_*.png, plus eval/fixtures/synthetic_manifest.json
recording the model, prompt, intended labels and token usage. Everything here
is labelled synthetic and must never be shown as real footage (CLAUDE.md
section 6). The "labels" are what we *asked for*, not verified ground truth.

    python eval/generate_synthetic_frames.py --dry-run    # print prompts only
    python eval/generate_synthetic_frames.py              # needs GEMINI_API_KEY in .env
    python eval/generate_synthetic_frames.py --only dead_branching --force
"""

from __future__ import annotations

import argparse
import base64
import json
import os
import time
from pathlib import Path

FIXTURES = Path(__file__).parent / "fixtures"
MANIFEST = FIXTURES / "synthetic_manifest.json"

STYLE = (
    "Photorealistic underwater photo from a downward-looking ROV camera about 1.5 m above "
    "the seabed, natural blue-green colour cast, slight turbidity and suspended particles, "
    "even lighting, no fish, no divers, no text or watermark."
)

# key -> (intended health_status, intended coral_type or "scene", prompt)
SHOTS: dict[str, tuple[str, str, str]] = {
    "live_acropora_branching": ("LIVE", "acropora_branching",
        "A single healthy staghorn Acropora colony with brown-tan pigmented tissue and pale growing tips, on rock."),
    "live_massive_meandering": ("LIVE", "massive_meandering",
        "A single healthy brain coral boulder with green-brown living tissue and clear meandering ridges, on rock."),
    "bleached_acropora_table": ("BLEACHED", "acropora_table",
        "A single bleached table Acropora: bright white, clean surface, tissue still present but pale, on rock."),
    "bleached_massive_meandering": ("BLEACHED", "massive_meandering",
        "A single bleached brain coral: stark white and smooth, still intact, surrounded by normal reef rock."),
    "dead_branching_other": ("DEAD", "branching_other",
        "A dead branching coral skeleton: grey-brown, covered in fuzzy algal turf, eroded broken tips."),
    "dead_massive_meandering": ("DEAD", "massive_meandering",
        "A dead brain coral boulder: dull grey skeleton covered in green-brown algal film, partly eroded."),
    "scene_mixed_health": ("MIXED", "scene",
        "A reef patch with several separate colonies: two healthy brown branching corals, one white "
        "bleached brain coral, and one grey algae-covered dead branching skeleton, on rock with sand gaps."),
    "scene_loose_fragments": ("MIXED", "scene",
        "Storm damage: four broken, loose branching coral fragments lying on sand and rubble, two with "
        "living brown tissue and two pale white, next to a patch of clean hard rock."),
}


def load_manifest() -> dict:
    return json.loads(MANIFEST.read_text()) if MANIFEST.exists() else {"synthetic": True, "images": {}}


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--only", nargs="*", choices=sorted(SHOTS), help="subset of shots to generate")
    p.add_argument("--force", action="store_true", help="regenerate even if the file exists")
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("--aspect-ratio", default="16:9")
    p.add_argument("--image-size", default="1K", choices=["512", "1K", "2K", "4K"])
    args = p.parse_args()

    from dotenv import load_dotenv

    load_dotenv()
    model = os.environ.get("GEMINI_MODEL_IMAGE_4K", "gemini-nano-banana-2.1")
    keys = args.only or list(SHOTS)
    FIXTURES.mkdir(parents=True, exist_ok=True)
    manifest = load_manifest()

    todo = [k for k in keys if args.force or not any(FIXTURES.glob(f"synthetic_{k}.*"))]
    print(f"model={model} generating {len(todo)} image(s), skipping {len(keys) - len(todo)} existing")
    if args.dry_run:
        for k in todo:
            print(f"- synthetic_{k}.png: {SHOTS[k][2]} {STYLE}")
        return
    if not todo:
        return
    if not os.environ.get("GEMINI_API_KEY"):
        raise SystemExit("GEMINI_API_KEY not set (put it in .env, never in the repo)")

    from google import genai

    client = genai.Client()
    for k in todo:
        health, ctype, subject = SHOTS[k]
        prompt = f"{subject} {STYLE}"
        t0 = time.perf_counter()
        try:
            interaction = client.interactions.create(
                model=model,
                input=prompt,
                api_version="v1beta",  # image_config is v1beta-only (400 on the default version)
                timeout=180,  # seconds; one call hung indefinitely without this
                generation_config={"image_config": {"aspect_ratio": args.aspect_ratio, "image_size": args.image_size}},
            )
        except Exception as e:  # one failed shot should not stop the rest; rerun to fill gaps
            print(f"! {k}: {type(e).__name__}: {e}")
            continue
        latency = time.perf_counter() - t0
        img = interaction.output_image
        if img is None or not img.data:
            print(f"! {k}: no image returned (status={interaction.status}, text={interaction.output_text!r})")
            continue
        ext = {"image/jpeg": "jpg", "image/webp": "webp"}.get(str(img.mime_type), "png")
        out = FIXTURES / f"synthetic_{k}.{ext}"
        out.write_bytes(base64.b64decode(img.data))
        usage = interaction.usage.model_dump(exclude_none=True) if interaction.usage else {}
        manifest["images"][out.name] = {
            "synthetic": True,
            "intended_health_status": health,
            "intended_coral_type": ctype,
            "model": model,
            "interaction_id": interaction.id,
            "prompt": prompt,
            "generated_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
            "latency_s": round(latency, 1),
            "usage": usage,
        }
        MANIFEST.write_text(json.dumps(manifest, indent=2))
        print(f"wrote {out.name} ({latency:.1f}s) usage={usage}")


if __name__ == "__main__":
    main()
