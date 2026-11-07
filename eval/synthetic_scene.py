"""Synthetic seabed for testing the mission FSM without Isaac Sim.

All output is synthetic test data, not sensor output. It produces
`SemanticMapEntry` rows (what perception would put in the registry) plus a
simple ground-truth shape per cluster that eval/mock_robot.py renders into
depth images.

Seeded by default (seed=0). Pass seed=None for an unseeded "live" scene.
"""

from __future__ import annotations

import copy
import dataclasses
from dataclasses import dataclass, field
from typing import Literal, Optional

import numpy as np

from agent.base_station import BaseStation, Rack
from perception.registry import SemanticMapEntry, SemanticSeabedRegistry

SPECIES = ("acropora_cervicornis", "porites_astreoides", "orbicella_faveolata")

ShapeKind = Literal["mound", "pillar"]


@dataclass(frozen=True)
class ShapeSpec:
    """Ground-truth geometry, seabed at z=0.

    mound:  z = height * (1 - (r/radius)^4), flat-topped with steep sides.
    pillar: thin vertical cylinder; its top is too small for a graft patch.
    """

    kind: ShapeKind
    center: tuple[float, float]
    radius: float
    height: float

    def bbox_extent(self) -> tuple[float, float, float]:
        return (2 * self.radius, 2 * self.radius, self.height)


@dataclass
class SyntheticScene:
    entries: list[SemanticMapEntry]
    shapes: dict[str, ShapeSpec]
    bounds: tuple[float, float, float, float]
    seed: Optional[int]
    synthetic: bool = field(default=True, init=False)

    def base_station(self) -> BaseStation:
        """Generous stock of every genet in the scene, just outside the survey area."""
        genets = sorted({(e.genet_id, e.species_class) for e in self.entries if e.genet_id})
        racks = [Rack(f"R{i:02d}", g, s, 50, 0.95) for i, (g, s) in enumerate(genets, start=1)]
        return BaseStation((-1.5, 5.0, 0.0), racks)

    def registry(self) -> SemanticSeabedRegistry:
        """Fresh registry with copies of the ground-truth entries."""
        reg = SemanticSeabedRegistry()
        for e in self.entries:
            reg.upsert(copy.deepcopy(e))
        return reg

    def entry(self, cluster_id: str) -> SemanticMapEntry:
        return next(e for e in self.entries if e.cluster_id == cluster_id)

    def ids(self, health_status: str) -> list[str]:
        return [e.cluster_id for e in self.entries if e.health_status == health_status]

    def add_cluster(
        self,
        cluster_id: str,
        species_class: str,
        health_status: str,
        health_score: float,
        center: tuple[float, float],
        radius: float = 0.14,
        height: float = 0.22,
        kind: ShapeKind = "mound",
        genet_id: Optional[str] = None,
    ) -> SemanticMapEntry:
        shape = ShapeSpec(kind, center, radius, height)
        entry = _entry_for(cluster_id, species_class, health_status, health_score, shape, genet_id)
        self.entries.append(entry)
        self.shapes[cluster_id] = shape
        return copy.deepcopy(entry)

    def make_pillar(self, cluster_id: str, radius: float = 0.01, height: float = 0.25) -> SemanticMapEntry:
        """Replace a cluster's geometry with a pillar (no valid graft patch)."""
        old = self.shapes[cluster_id]
        shape = ShapeSpec("pillar", old.center, radius, height)
        self.shapes[cluster_id] = shape
        i = next(i for i, e in enumerate(self.entries) if e.cluster_id == cluster_id)
        self.entries[i] = dataclasses.replace(
            self.entries[i],
            position_world=(old.center[0], old.center[1], height / 2.0),
            bounding_box_extent=shape.bbox_extent(),
        )
        return copy.deepcopy(self.entries[i])


def _entry_for(cluster_id, species_class, health_status, health_score, shape: ShapeSpec, genet_id=None) -> SemanticMapEntry:
    return SemanticMapEntry(
        cluster_id=cluster_id,
        species_class=species_class,
        health_status=health_status,
        health_score=round(float(health_score), 3),
        position_world=(round(shape.center[0], 4), round(shape.center[1], 4), round(shape.height / 2.0, 4)),
        bounding_box_extent=tuple(round(v, 4) for v in shape.bbox_extent()),
        genet_id=genet_id,
    )


def generate_scene(
    seed: Optional[int] = 0,
    n_clusters: Optional[int] = None,
    n_species: int = 3,
    bounds: tuple[float, float, float, float] = (0.0, 10.0, 0.0, 10.0),
    min_spacing: float = 0.8,
    edge_margin: float = 0.5,
) -> SyntheticScene:
    """15-20 clusters by default, 2-3 species, mixed LIVE/DEAD/BLEACHED.

    Each species has two genets, and every bleached colony has a known genet in
    stock, so every BLEACHED cluster is treatable unless a test breaks that.
    """
    rng = np.random.default_rng(seed)
    n = int(n_clusters if n_clusters is not None else rng.integers(15, 21))
    species = SPECIES[:n_species]
    xmin, xmax, ymin, ymax = bounds

    centers: list[tuple[float, float]] = []
    tries = 0
    while len(centers) < n:
        tries += 1
        if tries > 10_000:
            raise RuntimeError("could not place clusters; lower n_clusters or min_spacing")
        c = (
            float(rng.uniform(xmin + edge_margin, xmax - edge_margin)),
            float(rng.uniform(ymin + edge_margin, ymax - edge_margin)),
        )
        if all(np.hypot(c[0] - o[0], c[1] - o[1]) >= min_spacing for o in centers):
            centers.append(c)

    entries, shapes = [], {}
    for i, c in enumerate(centers):
        sp = species[i % len(species)] if i < len(species) else species[int(rng.integers(len(species)))]
        if i < len(species):
            status, score = "LIVE", rng.uniform(0.7, 0.98)  # guaranteed healthy donor per species
        else:
            status = rng.choice(["LIVE", "DEAD", "BLEACHED"], p=[0.3, 0.2, 0.5])
            score = {"LIVE": rng.uniform(0.4, 0.98), "DEAD": rng.uniform(0.0, 0.15), "BLEACHED": rng.uniform(0.2, 0.5)}[
                status
            ]
        shape = ShapeSpec("mound", c, float(rng.uniform(0.1, 0.18)), float(rng.uniform(0.15, 0.3)))
        cid = f"cluster_{i:02d}"
        genet_id = f"{sp}_g{int(rng.integers(2))}" if status == "BLEACHED" else None
        entries.append(_entry_for(cid, sp, str(status), score, shape, genet_id))
        shapes[cid] = shape
    return SyntheticScene(entries, shapes, bounds, seed)
