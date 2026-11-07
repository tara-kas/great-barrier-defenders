"""Genet identification from UV fluorescence (no model calls).

Genets are told apart by how a colony's fluorescence divides across three
emission bands. Same-genet contact is what makes symbiont transfer work, and a
wrong match harms the recipient, so anything short of a close match is no match.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable, Optional

import numpy as np

# RGB response of the UV camera to the cyan, green and red emission bands.
BANDS = np.array([[0.0, 0.85, 1.0], [0.2, 1.0, 0.3], [1.0, 0.2, 0.15]])
UV_BACKGROUND = np.array([0.02, 0.03, 0.09])

MATCH_MAX_DISTANCE = 0.15  # L1 distance between normalised signatures
MIN_GLOW = 0.15  # mean channel brightness below this reads as no fluorescence
MIN_GLOWING_PIXELS = 40

Signature = tuple[float, float, float]


@dataclass(frozen=True)
class GenetRecord:
    genet_id: str
    species_class: str
    signature: Signature


@dataclass(frozen=True)
class GenetMatch:
    genet_id: Optional[str]
    distance: Optional[float]
    nearest: Optional[str]

    def evidence(self) -> dict[str, Any]:
        return {"genet_id": self.genet_id, "distance": self.distance, "nearest": self.nearest}


def read_signature(uv: Any, box_xyxy: tuple[int, int, int, int]) -> Optional[Signature]:
    """Emission share per band inside a box, or None if too little of it glows."""
    x0, y0, x1, y1 = box_xyxy
    window = np.asarray(uv, dtype=float)[y0:y1, x0:x1].reshape(-1, 3) / 255.0
    glowing = window[window.mean(axis=1) > MIN_GLOW]
    if len(glowing) < MIN_GLOWING_PIXELS:
        return None
    shares = np.clip(np.median(glowing, axis=0) @ np.linalg.inv(BANDS), 0.0, None)
    if shares.sum() == 0:
        return None
    return tuple(round(float(v), 4) for v in shares / shares.sum())


def match_genet(
    species_class: str,
    signature: Signature,
    library: Iterable[GenetRecord],
    max_distance: float = MATCH_MAX_DISTANCE,
) -> GenetMatch:
    """Closest known genet of this species, if it is close enough to trust."""
    distances = {
        g.genet_id: float(np.abs(np.array(g.signature) - np.array(signature)).sum())
        for g in library
        if g.species_class == species_class
    }
    if not distances:
        return GenetMatch(None, None, None)
    nearest = min(distances, key=distances.get)
    distance = round(distances[nearest], 4)
    return GenetMatch(nearest if distance <= max_distance else None, distance, nearest)
