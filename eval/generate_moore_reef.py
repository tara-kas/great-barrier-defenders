"""Writes the Moore Reef dataset to data/moore_reef/.

    python eval/generate_moore_reef.py                # tiles are cached, frames are rebuilt
    python eval/generate_moore_reef.py --force-tiles  # new tiles: 13 Nano Banana calls

Colony tiles need GEMINI_API_KEY the first time. Everything else is deterministic.
"""

from __future__ import annotations

import argparse
import base64
import io
import json
import os
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any, Optional

import numpy as np
from PIL import Image

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:  # eval/ is not a package; make `agent`, `perception`, `eval` importable
    sys.path.insert(0, str(ROOT))

from agent.config import FSMConfig  # noqa: E402
from agent.fsm import lawnmower  # noqa: E402
from agent.robot_interface import Pose  # noqa: E402
from eval.mock_robot import DOWN_CAMERA  # noqa: E402
from eval.moore_reef import (  # noqa: E402
    BASE_STATION, BOUNDS, CONTACT_DAYS_REQUIRED, DATA_DIR, EXPECTED_ACTION, FRAME_CAMERA, GENETS,
    MATCH_MAX_DISTANCE, REVISIT_DAYS, SEED, SITE_DEPTH_M, TEXTURES, MooreReef, TextureSet,
    base_station_stock, build_reef, recovery_timeline, render_view,
)

MODEL = "gemini-nano-banana-2.1"
TILE_SIZE = 512
MIN_BOX_PX = 24
CROP_PAD = 0.12

VIEW = (
    "Photorealistic underwater photo looking straight down from directly above, the subject filling "
    "the whole square frame edge to edge, soft even light, no fish, no divers, no text or watermark."
)
FORMS = {
    "pocillopora": "a Pocillopora cauliflower coral colony with bushy, wart-covered branches",
    "acropora_branching": "a staghorn Acropora colony with many slender branches",
    "acropora_table": "a flat table Acropora colony with a fine plate surface",
    "massive_meandering": "a massive brain coral boulder with meandering ridges",
}
CONDITIONS = {
    "live": "Healthy living tissue, rich brown and tan pigment.",
    "bleached": "Bleached: bright white tissue, still intact and clean, with no algae.",
    "dead": "Dead: dull grey eroded skeleton covered in fuzzy green-brown algal turf.",
}


def tile_prompts() -> dict[str, str]:
    prompts = {"seabed": f"Great Barrier Reef seabed of pale coral rubble, sand and bare rock. {VIEW}"}
    for species, form in FORMS.items():
        for condition, text in CONDITIONS.items():
            prompts[f"{species}_{condition}"] = f"Close-up of {form}, on the Great Barrier Reef. {text} {VIEW}"
    return prompts


def make_tile(client: Any, name: str, prompt: str) -> tuple[str, Optional[dict], Optional[str]]:
    started = time.perf_counter()
    try:
        interaction = client.interactions.create(
            model=MODEL,
            input=prompt,
            api_version="v1beta",  # image_config is v1beta-only
            timeout=180,
            generation_config={"image_config": {"aspect_ratio": "1:1", "image_size": "1K"}},
        )
        image = interaction.output_image
        if image is None or not image.data:
            return name, None, f"no image returned (status {interaction.status})"
        decoded = Image.open(io.BytesIO(base64.b64decode(image.data))).convert("RGB")
        decoded.resize((TILE_SIZE, TILE_SIZE), Image.LANCZOS).save(TEXTURES / f"{name}.jpg", quality=88)
    except Exception as err:  # One failed tile should not lose the rest; rerun to fill gaps.
        return name, None, f"{type(err).__name__}: {err}"
    usage = interaction.usage
    return name, {
        "model": MODEL,
        "interaction_id": interaction.id,
        "prompt": prompt,
        "latency_s": round(time.perf_counter() - started, 1),
        "total_tokens": getattr(usage, "total_tokens", None),
    }, None


def generate_tiles(force: bool) -> None:
    TEXTURES.mkdir(parents=True, exist_ok=True)
    manifest_path = TEXTURES / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8")) if manifest_path.exists() else {}
    prompts = tile_prompts()
    todo = {k: p for k, p in prompts.items() if force or not (TEXTURES / f"{k}.jpg").exists()}
    if not todo:
        return

    from dotenv import load_dotenv
    from google import genai

    load_dotenv(ROOT / ".env")
    if not os.environ.get("GEMINI_API_KEY"):
        raise SystemExit("GEMINI_API_KEY is not set. Add it to .env.")
    client = genai.Client()
    print(f"Generating {len(todo)} tiles with {MODEL}...")
    with ThreadPoolExecutor(max_workers=4) as pool:
        results = list(pool.map(lambda kv: make_tile(client, *kv), todo.items()))
    failed = []
    for name, record, error in results:
        if record:
            manifest[name] = record
            print(f"  {name}: {record['latency_s']}s")
        else:
            failed.append(f"{name}: {error}")
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    if failed:
        raise SystemExit("Tiles failed, rerun to fill the gaps:\n  " + "\n  ".join(failed))


def write_json(path: Path, value: Any) -> None:
    path.write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")


def box_for(mask: np.ndarray) -> Optional[tuple[int, int, int, int]]:
    rows, cols = np.nonzero(mask)
    if rows.size == 0:
        return None
    box = (int(cols.min()), int(rows.min()), int(cols.max()) + 1, int(rows.max()) + 1)
    return box if min(box[2] - box[0], box[3] - box[1]) >= MIN_BOX_PX else None


def object_label(reef: MooreReef, index: int, box: tuple[int, int, int, int], width: int, height: int) -> dict:
    cluster = reef.clusters[index]
    x0, y0, x1, y1 = box
    return {
        "cluster_id": cluster.cluster_id,
        "box_xyxy": list(box),
        "box_2d": [round(y0 / height * 1000), round(x0 / width * 1000),
                   round(y1 / height * 1000), round(x1 / width * 1000)],
        "species_class": cluster.species_class,
        "health_status": cluster.health_status,
        "health_score": cluster.health_score,
        "genet_id": cluster.genet_id,
    }


def write_frames(reef: MooreReef, textures: TextureSet) -> dict[str, tuple[int, np.ndarray, np.ndarray, tuple]]:
    frames_dir = DATA_DIR / "frames"
    frames_dir.mkdir(parents=True, exist_ok=True)
    config = FSMConfig()
    waypoints = lawnmower(config.survey_bounds, config.survey_swath, config.seabed_z + config.hull_altitude)
    best: dict[str, tuple[int, np.ndarray, np.ndarray, tuple]] = {}
    rows = []
    for number, waypoint in enumerate(waypoints):
        pose = Pose(waypoint)
        view = render_view(reef, textures, pose)
        frame_id = f"frame_{number:03d}"
        Image.fromarray(view.rgb).save(frames_dir / f"{frame_id}_rgb.jpg", quality=88)
        Image.fromarray(view.uv).save(frames_dir / f"{frame_id}_uv.jpg", quality=90)
        Image.fromarray((view.depth * 1000).astype(np.uint16)).save(frames_dir / f"{frame_id}_depth.png")

        height, width = view.depth.shape
        objects = []
        for index in np.unique(view.cluster_index):
            if index < 0:
                continue
            mask = view.cluster_index == index
            box = box_for(mask)
            if box is None:
                continue
            objects.append(object_label(reef, int(index), box, width, height))
            cluster_id = reef.clusters[index].cluster_id
            area = int(mask.sum())
            if cluster_id not in best or area > best[cluster_id][0]:
                best[cluster_id] = (area, view.rgb, view.uv, box)
        rows.append({
            "frame_id": frame_id,
            "rgb": f"frames/{frame_id}_rgb.jpg",
            "uv": f"frames/{frame_id}_uv.jpg",
            "depth_mm": f"frames/{frame_id}_depth.png",
            "pose": {"position": list(pose.position), "orientation_quat": list(pose.orientation_quat)},
            "intrinsics": list(view.intrinsics),
            "camera_to_robot": DOWN_CAMERA.tolist(),
            "objects": objects,
        })
    (DATA_DIR / "frames.jsonl").write_text("\n".join(json.dumps(r) for r in rows) + "\n", encoding="utf-8")
    return best


def write_crops(reef: MooreReef, best: dict) -> int:
    crops_dir = DATA_DIR / "crops"
    crops_dir.mkdir(parents=True, exist_ok=True)
    rows = []
    for cluster_id, (_, rgb, uv, box) in sorted(best.items()):
        cluster = reef.cluster(cluster_id)
        x0, y0, x1, y1 = box
        pad_x, pad_y = int((x1 - x0) * CROP_PAD), int((y1 - y0) * CROP_PAD)
        window = (slice(max(y0 - pad_y, 0), y1 + pad_y), slice(max(x0 - pad_x, 0), x1 + pad_x))
        Image.fromarray(rgb[window]).save(crops_dir / f"{cluster_id}_rgb.jpg", quality=90)
        Image.fromarray(uv[window]).save(crops_dir / f"{cluster_id}_uv.jpg", quality=90)
        rows.append({
            "rgb": f"crops/{cluster_id}_rgb.jpg",
            "uv": f"crops/{cluster_id}_uv.jpg",
            **cluster.label(),
        })
    (DATA_DIR / "crops.jsonl").write_text("\n".join(json.dumps(r) for r in rows) + "\n", encoding="utf-8")
    return len(rows)


def write_dataset() -> None:
    reef = build_reef()
    textures = TextureSet()
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    write_json(DATA_DIR / "scenario.json", {
        "name": "Moore Reef",
        "region": "Great Barrier Reef, Queensland",
        "seed": SEED,
        "frame": "local metres, seabed datum at z = 0, +z up",
        "bounds": list(BOUNDS),
        "site_depth_m": SITE_DEPTH_M,
        "base_station": list(BASE_STATION),
        "rules": {
            "contact_days_required": CONTACT_DAYS_REQUIRED,
            "revisit_days": list(REVISIT_DAYS),
            "uv_match_max_l1_distance": MATCH_MAX_DISTANCE,
        },
        "camera": {"width": FRAME_CAMERA.width, "height": FRAME_CAMERA.height, "fov_deg": FRAME_CAMERA.fov_deg},
        "expected_actions": sorted(EXPECTED_ACTION.values()),
    })
    write_json(DATA_DIR / "registry.json", reef.scene.registry().dump())
    write_json(DATA_DIR / "labels.json", [c.label() for c in reef.clusters])
    write_json(DATA_DIR / "genets.json", {k: {**v, "signature": list(v["signature"])} for k, v in GENETS.items()})
    write_json(DATA_DIR / "base_station.json", base_station_stock())
    write_json(DATA_DIR / "recovery_timeline.json", recovery_timeline(reef))
    best = write_frames(reef, textures)
    crops = write_crops(reef, best)
    print(f"{len(reef.clusters)} clusters, {crops} crops, written to {DATA_DIR}")


def main(argv: Optional[list[str]] = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--force-tiles", action="store_true")
    args = parser.parse_args(argv)
    generate_tiles(args.force_tiles)
    write_dataset()


if __name__ == "__main__":
    main()
