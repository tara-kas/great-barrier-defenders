"""Coral detection: Gemma returns bounding boxes for every coral colony or
fragment in a full camera frame. Each box is then cropped and classified by
perception/classify.py and projected to world by perception/projection.py.

Box convention asked of the model: box_2d = [ymin, xmin, ymax, xmax],
normalised to 0-1000 (independent of image size, which the model only sees
after resizing). Parsing is pure and unit-tested with canned responses.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np

from perception.classify import extract_json_object
from perception.gemma_client import VisionLLM, encode_png


class DetectionError(ValueError):
    pass


@dataclass(frozen=True)
class Detection:
    box_xyxy: tuple[int, int, int, int]  # pixel coords in the original frame
    label: str


DETECT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "objects": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "label": {"type": "string"},
                    "box_2d": {"type": "array", "items": {"type": "integer"}, "minItems": 4, "maxItems": 4},
                },
                "required": ["label", "box_2d"],
            },
        }
    },
    "required": ["objects"],
}

DETECT_PROMPT = """You are the perception module of an underwater coral-restoration robot.
Find every coral colony or loose coral fragment in this seabed image, whether
living, bleached (white) or dead (grey, algae-covered skeleton). Ignore bare
rock, sand, rubble, fish, sponges and equipment.

Return a JSON object {"objects": [{"label": "...", "box_2d": [ymin, xmin, ymax, xmax]}, ...]}
where box_2d is normalised to 0-1000 and label is a 1-3 word description.
Return {"objects": []} if there is no coral. Output only the JSON."""


def _iou(a: tuple[int, int, int, int], b: tuple[int, int, int, int]) -> float:
    ix = max(0, min(a[2], b[2]) - max(a[0], b[0]))
    iy = max(0, min(a[3], b[3]) - max(a[1], b[1]))
    inter = ix * iy
    union = (a[2] - a[0]) * (a[3] - a[1]) + (b[2] - b[0]) * (b[3] - b[1]) - inter
    return inter / union if union > 0 else 0.0


def parse_detections(
    text: str, width: int, height: int, min_side_px: int = 8, dedupe_iou: float = 0.7
) -> list[Detection]:
    stripped = text.strip()
    if stripped.startswith("[") or stripped.startswith("```json\n["):
        text = '{"objects": ' + stripped.strip("`").removeprefix("json").strip() + "}"
    obj = extract_json_object(text)
    items = obj.get("objects")
    if not isinstance(items, list):
        raise DetectionError(f"'objects' is not a list: {obj}")

    out: list[Detection] = []
    for it in items:
        if not isinstance(it, dict):
            continue
        box = it.get("box_2d")
        if not (isinstance(box, (list, tuple)) and len(box) == 4):
            continue
        try:
            ymin, xmin, ymax, xmax = (float(v) for v in box)
        except (TypeError, ValueError):
            continue
        if ymin > ymax:
            ymin, ymax = ymax, ymin
        if xmin > xmax:
            xmin, xmax = xmax, xmin
        x0 = int(np.clip(xmin / 1000 * width, 0, width))
        x1 = int(np.clip(xmax / 1000 * width, 0, width))
        y0 = int(np.clip(ymin / 1000 * height, 0, height))
        y1 = int(np.clip(ymax / 1000 * height, 0, height))
        if x1 - x0 < min_side_px or y1 - y0 < min_side_px:
            continue
        b = (x0, y0, x1, y1)
        if any(_iou(b, d.box_xyxy) > dedupe_iou for d in out):
            continue
        out.append(Detection(box_xyxy=b, label=str(it.get("label", "coral"))))
    return out


def detect_corals(llm: VisionLLM, rgb: Any) -> tuple[list[Detection], float]:
    """Returns (detections, latency_ms)."""
    a = np.asarray(rgb)
    h, w = a.shape[:2]
    reply = llm.ask(DETECT_PROMPT, encode_png(a, max_side=1024), json_schema=DETECT_SCHEMA)
    return parse_detections(reply.text, w, h), reply.latency_ms
