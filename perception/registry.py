"""Semantic Seabed Registry: the shared data contract perception, agent, and
dashboard all read/write. Schema matches the spec PDF section 5.1 exactly.
"""

from dataclasses import asdict, dataclass
from typing import Literal, Optional

HealthStatus = Literal["LIVE", "DEAD", "BLEACHED", "RESTORED"]


@dataclass
class GraftPose:
    position: tuple[float, float, float]
    orientation_quat: tuple[float, float, float, float]
    surface_normal: tuple[float, float, float]


@dataclass
class SemanticMapEntry:
    cluster_id: str
    species_class: str
    health_status: HealthStatus
    health_score: float
    position_world: tuple[float, float, float]
    bounding_box_extent: tuple[float, float, float]
    optimal_graft_pose_world: Optional[GraftPose] = None
    sampled_or_restored: bool = False

    def to_dict(self) -> dict:
        return asdict(self)


class SemanticSeabedRegistry:
    def __init__(self) -> None:
        self._entries: dict[str, SemanticMapEntry] = {}

    def upsert(self, entry: SemanticMapEntry) -> None:
        self._entries[entry.cluster_id] = entry

    def get(self, cluster_id: str) -> Optional[SemanticMapEntry]:
        return self._entries.get(cluster_id)

    def all(self) -> list[SemanticMapEntry]:
        return list(self._entries.values())

    def query(
        self,
        health_status: Optional[str] = None,
        species_class: Optional[str] = None,
    ) -> list[SemanticMapEntry]:
        results = list(self._entries.values())
        if health_status is not None:
            results = [e for e in results if e.health_status == health_status]
        if species_class is not None:
            results = [e for e in results if e.species_class == species_class]
        return results

    def dump(self) -> list[dict]:
        return [e.to_dict() for e in self._entries.values()]
