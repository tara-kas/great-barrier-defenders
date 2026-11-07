"""Helpers that turn live objects into JSON-safe decision-log evidence.

One schema for poses and registry entries, so the dashboard and the Argon
debrief can parse evidence without per-state special cases.
"""

from __future__ import annotations

import dataclasses
import math
from typing import Any

import numpy as np

from agent.robot_interface import Pose
from perception.registry import SemanticMapEntry


def to_jsonable(obj: Any) -> Any:
    """Recursively convert numpy types, dataclasses and tuples to plain JSON types."""
    if dataclasses.is_dataclass(obj) and not isinstance(obj, type):
        return to_jsonable(dataclasses.asdict(obj))
    if isinstance(obj, dict):
        return {str(k): to_jsonable(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple, set)):
        return [to_jsonable(v) for v in obj]
    if isinstance(obj, np.ndarray):
        return to_jsonable(obj.tolist())
    if isinstance(obj, np.generic):
        return to_jsonable(obj.item())
    if isinstance(obj, float):
        return round(obj, 6) if math.isfinite(obj) else None
    return obj


def pose_summary(pose: Pose) -> dict:
    return {
        "position": [round(float(v), 4) for v in pose.position],
        "orientation_quat": [round(float(v), 4) for v in pose.orientation_quat],
    }


def entry_summary(entry: SemanticMapEntry) -> dict:
    return {
        "cluster_id": entry.cluster_id,
        "species_class": entry.species_class,
        "health_status": entry.health_status,
        "health_score": round(float(entry.health_score), 4),
        "position_world": [round(float(v), 4) for v in entry.position_world],
        "sampled_or_restored": entry.sampled_or_restored,
        "genet_id": entry.genet_id,
    }
