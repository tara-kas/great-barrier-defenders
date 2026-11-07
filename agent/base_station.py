"""The base station: racks of healthy coral propagated for each genet (pure, no I/O)."""

from __future__ import annotations

import json
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Iterable, Optional


@dataclass(frozen=True)
class Rack:
    slot: str
    genet_id: str
    species_class: str
    fragments_available: int
    health_score: float


class BaseStation:
    def __init__(self, position: tuple[float, float, float], racks: Iterable[Rack]) -> None:
        self.position = tuple(float(v) for v in position)
        self._racks = {r.genet_id: r for r in racks}

    @staticmethod
    def load(path: Path) -> "BaseStation":
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        fields = ("slot", "genet_id", "species_class", "fragments_available", "health_score")
        return BaseStation(tuple(data["position_world"]), [Rack(**{k: r[k] for k in fields}) for r in data["racks"]])

    def rack_for(self, genet_id: str) -> Optional[Rack]:
        return self._racks.get(genet_id)

    def available(self, genet_id: str) -> int:
        rack = self.rack_for(genet_id)
        return rack.fragments_available if rack else 0

    def take(self, genet_id: str) -> Rack:
        rack = self._racks[genet_id]
        if rack.fragments_available <= 0:
            raise ValueError(f"no fragments of {genet_id} left")
        self._racks[genet_id] = replace(rack, fragments_available=rack.fragments_available - 1)
        return rack

    def put_back(self, genet_id: str) -> None:
        rack = self._racks[genet_id]
        self._racks[genet_id] = replace(rack, fragments_available=rack.fragments_available + 1)

    def stock(self) -> dict[str, int]:
        return {g: r.fragments_available for g, r in sorted(self._racks.items())}
