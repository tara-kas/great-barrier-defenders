"""Measure perception/classify.py accuracy on real reef photos (Coralscapes).

Coralscapes (EPFL-ECEO/coralscapes, Apache 2.0) is a semantic-segmentation
dataset: each pixel has one of 39 classes, several of which encode coral type
AND health ("branching dead", "table acropora alive", ...). We cut crops around
connected regions of those classes and ask Gemma to classify each crop.

What this measures: zero-shot health (LIVE / BLEACHED / DEAD) and coral-type
accuracy on real underwater photos. What it does NOT measure: sim-to-real
transfer, or accuracy on our Isaac Sim renders (CLAUDE.md section 6).

    python eval/coralscapes_eval.py --dry-run           # build crops only, no Gemma calls
    python eval/coralscapes_eval.py --n-crops 45        # needs GEMMA_BASE_URL

Results JSON goes to eval/runs/ (git-ignored).
"""

from __future__ import annotations

import argparse
import json
import logging
import statistics
import sys
import time
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path

import numpy as np
from scipy import ndimage

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from perception.classify import HEALTH_VALUES, ClassificationError, classify_crop  # noqa: E402

DATASET = "EPFL-ECEO/coralscapes"
HEALTH_WORDS = {"alive": "LIVE", "bleached": "BLEACHED", "dead": "DEAD"}
TYPE_PREFIXES = {
    "table acropora": "acropora_table",
    "acropora": "acropora_branching",
    "pocillopora": "pocillopora",
    "stylophora": "stylophora",
    "branching": "branching_other",
    "massive/meandering": "massive_meandering",
    "meandering": "massive_meandering",
    "other coral": "other_coral",
}
# A "branching" annotation only fixes the growth form, so any branching genus counts.
BRANCHING = {"acropora_branching", "pocillopora", "stylophora", "branching_other"}


def class_map(id2label: dict[str, str]) -> dict[int, tuple[str, str, str]]:
    """class id -> (dataset name, our coral type, our health) for coral classes with a health suffix."""
    out = {}
    for cid, name in id2label.items():
        words = name.rsplit(" ", 1)
        if len(words) != 2 or words[1] not in HEALTH_WORDS or name == "dead clam":
            continue
        ctype = TYPE_PREFIXES.get(words[0])
        if ctype:
            out[int(cid)] = (name, ctype, HEALTH_WORDS[words[1]])
    return out


def type_correct(pred: str, gt: str) -> bool | None:
    if gt == "other_coral":
        return None  # genus unknown in the label: not scored
    if gt == "branching_other":
        return pred in BRANCHING
    return pred == gt


@dataclass
class Sample:
    image_idx: int
    class_name: str
    gt_type: str
    gt_health: str
    box_xyxy: tuple[int, int, int, int]
    area_px: int
    crop: np.ndarray


def crops_from_image(idx, rgb, mask, cmap, min_area_frac, max_per_image, pad=0.1) -> list[Sample]:
    h, w = mask.shape
    found = []
    for cid, (name, ctype, health) in cmap.items():
        comp, n = ndimage.label(mask == cid)
        if n == 0:
            continue
        areas = ndimage.sum_labels(np.ones_like(comp), comp, index=np.arange(1, n + 1))
        for k, sl in enumerate(ndimage.find_objects(comp)):
            if areas[k] < min_area_frac * h * w:
                continue
            y0, y1, x0, x1 = sl[0].start, sl[0].stop, sl[1].start, sl[1].stop
            px, py = int((x1 - x0) * pad), int((y1 - y0) * pad)
            box = (max(0, x0 - px), max(0, y0 - py), min(w, x1 + px), min(h, y1 + py))
            found.append(Sample(idx, name, ctype, health, box, int(areas[k]), rgb[box[1] : box[3], box[0] : box[2]]))
    # Keep the largest regions per health state, so a big live colony does not
    # crowd out a smaller bleached one in the same image.
    found.sort(key=lambda s: -s.area_px)
    kept, per_health = [], Counter()
    for s in found:
        if per_health[s.gt_health] < max_per_image:
            kept.append(s)
            per_health[s.gt_health] += 1
    return kept


def collect(args) -> list[Sample]:
    from datasets import load_dataset
    from huggingface_hub import hf_hub_download

    id2label = json.loads(Path(hf_hub_download(DATASET, "id2label.json", repo_type="dataset")).read_text())
    cmap = class_map(id2label)
    print(f"scoring {len(cmap)} coral classes: {sorted(v[0] for v in cmap.values())}")

    by_health: dict[str, list[Sample]] = defaultdict(list)
    ds = load_dataset(DATASET, split=args.split, streaming=True)
    for i, row in enumerate(ds):
        if i >= args.max_images:
            break
        rgb = np.asarray(row["image"].convert("RGB"))
        mask = np.asarray(row["label"])
        for s in crops_from_image(i, rgb, mask, cmap, args.min_area_frac, args.max_per_image):
            by_health[s.gt_health].append(s)

    # Round-robin across health states so the rarer BLEACHED class is represented.
    samples: list[Sample] = []
    queues = [list(by_health[hv]) for hv in HEALTH_VALUES]
    while len(samples) < args.n_crops and any(queues):
        for q in queues:
            if q and len(samples) < args.n_crops:
                samples.append(q.pop(0))
    return samples


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--split", default="validation")
    p.add_argument("--n-crops", type=int, default=45)
    p.add_argument("--max-images", type=int, default=166)
    p.add_argument("--max-per-image", type=int, default=2, help="max crops per health state per image")
    p.add_argument("--min-area-frac", type=float, default=0.003)
    p.add_argument("--min-confidence", type=float, default=0.6)
    p.add_argument("--dry-run", action="store_true", help="build crops and print class balance, no Gemma calls")
    p.add_argument("--save-crops", action="store_true", help="also write crops to eval/runs/<run>/")
    args = p.parse_args()
    logging.basicConfig(level=logging.WARNING, format="%(levelname)s %(message)s")
    for noisy in ("httpx", "httpcore", "huggingface_hub", "fsspec", "datasets"):
        logging.getLogger(noisy).setLevel(logging.WARNING)

    samples = collect(args)
    print(f"collected {len(samples)} crops; health balance: {dict(Counter(s.gt_health for s in samples))}")
    print(f"classes: {dict(Counter(s.class_name for s in samples))}")

    run_dir = Path(__file__).parent / "runs" / f"coralscapes_{time.strftime('%Y%m%d_%H%M%S')}"
    if args.save_crops or args.dry_run:
        from PIL import Image

        run_dir.mkdir(parents=True, exist_ok=True)
        for k, s in enumerate(samples):
            Image.fromarray(s.crop).save(run_dir / f"{k:03d}_{s.class_name.replace('/', '-').replace(' ', '_')}.jpg")
        print(f"crops saved to {run_dir}")
    if args.dry_run:
        return

    from perception.gemma_client import GemmaClient

    client = GemmaClient()
    rows = []
    for k, s in enumerate(samples):
        row = {"k": k, "image_idx": s.image_idx, "class_name": s.class_name, "gt_type": s.gt_type,
               "gt_health": s.gt_health, "box_xyxy": s.box_xyxy}
        try:
            r = classify_crop(client, s.crop)
            row.update(pred_type=r.species_class, pred_health=r.health_status, confidence=r.confidence,
                       is_coral=r.is_coral, evidence=r.evidence, latency_ms=r.latency_ms,
                       abstain=r.should_abstain(args.min_confidence))
        except ClassificationError as e:
            row.update(error=str(e), abstain=True)
        rows.append(row)
        print(f"[{k + 1}/{len(samples)}] gt={s.gt_health:<8} pred={row.get('pred_health', 'ERR'):<8} "
              f"conf={row.get('confidence', 0):.2f} {s.class_name}")

    scored = [r for r in rows if "pred_health" in r]
    answered = [r for r in scored if not r["abstain"]]
    typed = [(r, type_correct(r["pred_type"], r["gt_type"])) for r in scored]
    typed = [ok for _, ok in typed if ok is not None]
    lat = [r["latency_ms"] for r in scored]

    def acc(rs):
        return sum(r["pred_health"] == r["gt_health"] for r in rs) / len(rs) if rs else float("nan")

    confusion = {gt: {pr: sum(1 for r in scored if r["gt_health"] == gt and r["pred_health"] == pr)
                      for pr in HEALTH_VALUES} for gt in HEALTH_VALUES}
    abstained = [r for r in scored if r["abstain"]]
    summary = {
        "dataset": f"{DATASET}:{args.split}",
        "model": client.model,
        "n_crops": len(rows),
        "parse_errors": len(rows) - len(scored),
        "health_accuracy_all": acc(scored),
        "health_accuracy_when_not_abstaining": acc(answered),
        "abstention_rate": len(abstained) / len(scored) if scored else float("nan"),
        "abstained_would_have_been_wrong": (sum(r["pred_health"] != r["gt_health"] for r in abstained) / len(abstained)) if abstained else None,
        "type_accuracy_where_labelled": (sum(typed) / len(typed)) if typed else None,
        "n_type_scored": len(typed),
        "health_confusion_gt_rows_pred_cols": confusion,
        "latency_ms_mean": statistics.mean(lat) if lat else None,
        "latency_ms_p95": float(np.percentile(lat, 95)) if lat else None,
        "caveat": "Real underwater photos, zero-shot. Not a measure of sim-to-real transfer.",
    }
    run_dir.mkdir(parents=True, exist_ok=True)
    (run_dir / "results.json").write_text(json.dumps({"summary": summary, "rows": rows}, indent=2))
    print(json.dumps(summary, indent=2))
    print(f"\nHealth accuracy: {summary['health_accuracy_all']:.1%} on {len(scored)} crops "
          f"({summary['health_accuracy_when_not_abstaining']:.1%} when not abstaining). Saved {run_dir}/results.json")


if __name__ == "__main__":
    main()
