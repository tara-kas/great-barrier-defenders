"""Donor inventory: legacy station racks or positioned living reef sources."""

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
    position_world: Optional[tuple[float, float, float]] = None
    source_kind: str = "base_station"
    fragment_ids: tuple[str, ...] = ()


class BaseStation:
    def __init__(self, position: tuple[float, float, float], racks: Iterable[Rack]) -> None:
        self.position = tuple(float(v) for v in position)
        racks = list(racks)
        self._racks = {r.slot: r for r in racks}
        if len(self._racks) != len(racks):
            raise ValueError("donor source slots must be unique")
        for rack in racks:
            if rack.source_kind == "living_reef" and rack.position_world is None:
                raise ValueError("living reef sources require position_world")
            if rack.fragment_ids and len(rack.fragment_ids) != rack.fragments_available:
                raise ValueError("fragment_ids must describe every available fragment")
        ids = [fid for rack in racks for fid in rack.fragment_ids]
        if len(ids) != len(set(ids)):
            raise ValueError("fragment IDs must be unique across donor sources")

    @staticmethod
    def load(path: Path) -> "BaseStation":
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        fields = ("slot", "genet_id", "species_class", "fragments_available", "health_score")
        racks = []
        for r in data["racks"]:
            values = {k: r[k] for k in fields}
            values.update({k: r[k] for k in ("position_world", "source_kind", "fragment_ids") if k in r})
            for key in ("position_world", "fragment_ids"):
                if values.get(key) is not None:
                    values[key] = tuple(values[key])
            racks.append(Rack(**values))
        return BaseStation(tuple(data["position_world"]), racks)

    def sources_for(self, genet_id: str) -> tuple[Rack, ...]:
        return tuple(r for r in self._racks.values() if r.genet_id == genet_id)

    def rack_for(self, genet_id: str, slot: Optional[str] = None) -> Optional[Rack]:
        sources = self.sources_for(genet_id)
        if slot is not None:
            return next((r for r in sources if r.slot == slot), None)
        return next((r for r in sources if r.fragments_available > 0), sources[0] if sources else None)

    def position_for(self, rack: Rack) -> tuple[float, float, float]:
        return tuple(rack.position_world) if rack.position_world is not None else self.position

    def available(self, genet_id: str) -> int:
        return sum(r.fragments_available for r in self.sources_for(genet_id))

    def take(self, genet_id: str, slot: Optional[str] = None, fragment_id: Optional[str] = None) -> Rack:
        rack = self.rack_for(genet_id, slot)
        if rack is None:
            raise KeyError(genet_id)
        if rack.fragments_available <= 0:
            raise ValueError(f"no fragments of {genet_id} left")
        ids = rack.fragment_ids
        if ids:
            fragment_id = fragment_id or ids[0]
            if fragment_id not in ids:
                raise ValueError("fragment is not available at selected source")
            ids = tuple(fid for fid in ids if fid != fragment_id)
        self._racks[rack.slot] = replace(rack, fragments_available=rack.fragments_available - 1, fragment_ids=ids)
        return rack

    def put_back(self, genet_id: str, slot: Optional[str] = None, fragment_id: Optional[str] = None) -> None:
        rack = self.rack_for(genet_id, slot)
        if rack is None:
            raise KeyError(genet_id)
        ids = rack.fragment_ids + ((fragment_id,) if fragment_id else ())
        if len(ids) != len(set(ids)):
            raise ValueError("fragment already in source inventory")
        self._racks[rack.slot] = replace(rack, fragments_available=rack.fragments_available + 1, fragment_ids=ids)

    def stock(self) -> dict[str, int]:
        return {g: self.available(g) for g in sorted({r.genet_id for r in self._racks.values()})}
