"""Coral type + health classification: Gemma prompted zero-shot on an RGB crop.

No training. The prompt/parse contract is pure and typed so it is unit-tested
against canned responses (perception/tests/test_classify.py); the only network
call is GemmaClient.ask, which goes to a self-hosted endpoint.

`species_class` is genus / growth-form level, not species or genet: that is
what is visually separable and what Coralscapes labels (see CORAL_TYPES).

Live check:
    python -m perception.classify eval/fixtures/<image>.png [--box x0 y0 x1 y1]
"""

from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass
from typing import Any, Literal, Optional

from perception.gemma_client import GemmaReply, VisionLLM, encode_png

Health = Literal["LIVE", "BLEACHED", "DEAD"]
HEALTH_VALUES: tuple[str, ...] = ("LIVE", "BLEACHED", "DEAD")

CORAL_TYPES: tuple[str, ...] = (
    "acropora_branching",  # staghorn-style branching Acropora
    "acropora_table",  # flat plate / table Acropora
    "pocillopora",  # cauliflower / bushy, wart-covered branches
    "stylophora",  # short, stubby, blunt-tipped branches
    "branching_other",  # branching, genus unclear
    "massive_meandering",  # boulder, brain, meandering ridges
    "other_coral",  # encrusting, foliose, soft, anything else
)

# Loose synonyms Gemma might use -> canonical type.
_TYPE_SYNONYMS: dict[str, str] = {
    "acropora": "acropora_branching",
    "staghorn": "acropora_branching",
    "branching_acropora": "acropora_branching",
    "table_acropora": "acropora_table",
    "tabular_acropora": "acropora_table",
    "plate_acropora": "acropora_table",
    "table": "acropora_table",
    "cauliflower": "pocillopora",
    "branching": "branching_other",
    "massive": "massive_meandering",
    "meandering": "massive_meandering",
    "brain": "massive_meandering",
    "brain_coral": "massive_meandering",
    "boulder": "massive_meandering",
    "other": "other_coral",
    "unknown": "other_coral",
}

# Plausible health_score band per status; outside it we keep the status (the
# categorical answer) and clamp the score into the band.
_SCORE_BANDS: dict[str, tuple[float, float]] = {
    "LIVE": (0.6, 1.0),
    "BLEACHED": (0.2, 0.7),
    "DEAD": (0.0, 0.3),
}

RESPONSE_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "evidence": {"type": "string"},
        "is_coral": {"type": "boolean"},
        "coral_type": {"type": "string", "enum": list(CORAL_TYPES)},
        "health_status": {"type": "string", "enum": list(HEALTH_VALUES)},
        "health_score": {"type": "number"},
        "confidence": {"type": "number"},
    },
    "required": ["evidence", "is_coral", "coral_type", "health_status", "health_score", "confidence"],
}

PROMPT = f"""You are the perception module of an underwater coral-restoration robot.
The image is a crop around one object on the reef. Classify it.

Fields:
- evidence: one short sentence naming the visual cues you used (tissue colour,
  polyp texture, bare white skeleton, algal film, shape).
- is_coral: false if the object is rock, sand, rubble, sponge, algae, fish or
  equipment rather than a coral colony or fragment.
- coral_type: one of {", ".join(CORAL_TYPES)}.
- health_status:
    LIVE      = pigmented living tissue (brown, green, tan, purple...).
    BLEACHED  = living tissue present but white/pale; skeleton visible through
                translucent tissue, surface still clean and smooth.
    DEAD      = no living tissue; bare skeleton, often greyish, covered in
                algal film or turf, eroded or broken.
- health_score: 0.0 to 1.0 vitality. LIVE 0.6-1.0, BLEACHED 0.2-0.7, DEAD 0.0-0.3.
- confidence: 0.0 to 1.0, how sure you are of health_status. Be honest: use a
  low value for blurry, dark, turbid, or partly occluded crops.

Reply with a single JSON object with exactly these keys and nothing else."""


class ClassificationError(ValueError):
    """Model output could not be parsed into a valid classification."""


@dataclass
class ClassificationResult:
    species_class: str
    health_status: Health
    health_score: float
    confidence: float
    is_coral: bool
    evidence: str
    raw_text: str = ""
    latency_ms: float = 0.0

    def should_abstain(self, min_confidence: float = 0.6) -> bool:
        """CLAUDE.md section 4: never act on a fragment it cannot classify confidently."""
        return (not self.is_coral) or self.confidence < min_confidence

    def to_evidence(self) -> dict[str, Any]:
        d = asdict(self)
        d.pop("raw_text")
        return d


def _slug(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", s.strip().lower()).strip("_")


def normalise_type(raw: Any) -> str:
    s = _slug(str(raw or ""))
    if s in CORAL_TYPES:
        return s
    if s in _TYPE_SYNONYMS:
        return _TYPE_SYNONYMS[s]
    for key, canon in _TYPE_SYNONYMS.items():
        if key in s:
            return canon
    return "other_coral"


def _to_float(x: Any, name: str) -> float:
    try:
        v = float(x)
    except (TypeError, ValueError):
        raise ClassificationError(f"{name} is not a number: {x!r}")
    if v != v:  # NaN
        raise ClassificationError(f"{name} is NaN")
    return v


def _to_bool(x: Any) -> bool:
    if isinstance(x, bool):
        return x
    if isinstance(x, str):
        return x.strip().lower() in ("true", "yes", "1")
    return bool(x)


def extract_json_object(text: str) -> dict[str, Any]:
    """First JSON object in text, tolerating ```json fences and surrounding prose."""
    dec = json.JSONDecoder()
    for m in re.finditer(r"\{", text):
        try:
            obj, _ = dec.raw_decode(text, m.start())
        except json.JSONDecodeError:
            continue
        if isinstance(obj, dict):
            return obj
    raise ClassificationError(f"no JSON object in model output: {text[:200]!r}")


def parse_response(text: str) -> ClassificationResult:
    obj = extract_json_object(text)
    missing = [k for k in ("health_status", "confidence") if k not in obj]
    if missing:
        raise ClassificationError(f"missing keys {missing} in {obj}")

    status = str(obj["health_status"]).strip().upper()
    if status in ("HEALTHY", "ALIVE"):
        status = "LIVE"
    if status not in HEALTH_VALUES:
        raise ClassificationError(f"unknown health_status {obj['health_status']!r}")

    lo, hi = _SCORE_BANDS[status]
    default_score = (lo + hi) / 2
    score = _to_float(obj.get("health_score", default_score), "health_score")
    if score > 1.0 and score <= 100.0:  # model answered in percent
        score /= 100.0
    score = min(max(score, lo), hi)

    conf = _to_float(obj["confidence"], "confidence")
    if conf > 1.0 and conf <= 100.0:
        conf /= 100.0
    conf = min(max(conf, 0.0), 1.0)

    return ClassificationResult(
        species_class=normalise_type(obj.get("coral_type")),
        health_status=status,  # type: ignore[arg-type]
        health_score=round(score, 3),
        confidence=round(conf, 3),
        is_coral=_to_bool(obj.get("is_coral", True)),
        evidence=str(obj.get("evidence", "")).strip(),
        raw_text=text,
    )


def classify_crop(llm: VisionLLM, crop_rgb: Any) -> ClassificationResult:
    """Classify one RGB crop (HxWx3 uint8 array or PIL image). Raises
    ClassificationError on unparseable output; callers should treat that as
    'abstain', not retry in a loop."""
    reply: GemmaReply = llm.ask(PROMPT, encode_png(crop_rgb), json_schema=RESPONSE_SCHEMA)
    result = parse_response(reply.text)
    result.latency_ms = reply.latency_ms
    return result


def crop_box(rgb: Any, box_xyxy: tuple[int, int, int, int], pad_frac: float = 0.1) -> Any:
    """Crop with a little context padding, clipped to the image."""
    import numpy as np

    a = np.asarray(rgb)
    h, w = a.shape[:2]
    x0, y0, x1, y1 = box_xyxy
    px, py = int((x1 - x0) * pad_frac), int((y1 - y0) * pad_frac)
    return a[max(0, y0 - py) : min(h, y1 + py), max(0, x0 - px) : min(w, x1 + px)]


def _main(argv: Optional[list[str]] = None) -> None:
    import argparse
    import logging

    import numpy as np
    from PIL import Image

    from perception.gemma_client import GemmaClient

    p = argparse.ArgumentParser(description="One live Gemma classification of an image or crop.")
    p.add_argument("image")
    p.add_argument("--box", nargs=4, type=int, metavar=("X0", "Y0", "X1", "Y1"))
    args = p.parse_args(argv)
    logging.basicConfig(level=logging.INFO)

    rgb = np.asarray(Image.open(args.image).convert("RGB"))
    if args.box:
        rgb = crop_box(rgb, tuple(args.box))
    client = GemmaClient()
    res = classify_crop(client, rgb)
    print(json.dumps({**res.to_evidence(), "model": client.model, "raw_text": res.raw_text}, indent=2))


if __name__ == "__main__":
    _main()
