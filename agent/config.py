"""Tunable parameters for the mission FSM, in one place.

Everything the Argon debrief might propose changing (pairing weights,
thresholds, stand-offs) lives here as plain frozen dataclasses with
`to_dict` / `from_dict`, so a patch is a config diff rather than a code diff,
and the regression suite (eval/test_fsm_loop.py) can run it directly.
"""

from __future__ import annotations

import dataclasses
import math
from dataclasses import dataclass, field
from numbers import Real
from typing import Any, Optional


def _finite_fields(config: Any) -> None:
    """Reject invalid numeric values before they reach control calculations."""
    for item in dataclasses.fields(config):
        value = getattr(config, item.name)
        if dataclasses.is_dataclass(value):
            continue
        values = value if isinstance(value, (tuple, list)) else (value,)
        for number in values:
            try:
                valid = isinstance(number, Real) and not isinstance(number, bool) and math.isfinite(number)
            except OverflowError:
                valid = False
            if not valid:
                raise ValueError(f"{item.name} must contain finite numeric values")


def _positive_counts(config: Any, *names: str) -> None:
    for name in names:
        value = getattr(config, name)
        if not isinstance(value, int) or isinstance(value, bool) or value <= 0:
            raise ValueError(f"{name} must be a positive integer")


@dataclass(frozen=True)
class PairingWeights:
    """J(i, j) = w1*|x_rov - x_i| + w2*|x_i - x_j| - w3*H_i"""

    w1: float = 1.0  # ROV -> donor travel
    w2: float = 1.5  # donor -> recipient transfer (carry leg)
    w3: float = 2.0  # donor health reward

    def __post_init__(self) -> None:
        _finite_fields(self)


@dataclass(frozen=True)
class GraftConfig:
    """Parameters for agent/graft_point.py (PCA graft/harvest point selector)."""

    k_neighbors: int = 15
    min_up_dot: float = 0.866  # cos 30 deg
    height_percentile: float = 50.0
    approach_length: float = 0.15  # m, cylinder along the normal that must be clear
    approach_radius: float = 0.02  # m
    approach_clearance: float = 0.01  # m, ignore points this close along the normal (own surface)
    reach_radius: float = 0.6  # m, from the reach centre (manipulator base)
    patch_connect_radius: float = 0.015  # m, neighbour distance for contiguous patches
    min_patch_points: int = 20
    max_candidates: int = 3
    tool_axis: tuple[float, float, float] = (0.0, 0.0, 1.0)  # end-effector approach axis

    def __post_init__(self) -> None:
        _finite_fields(self)
        _positive_counts(self, "k_neighbors", "min_patch_points", "max_candidates")


@dataclass(frozen=True)
class NavConfig:
    dt: float = 0.1  # s between control ticks (simulated time, not wall-clock)
    position_tolerance: float = 0.05  # m
    gain: float = 1.0  # P-gain, 1/s
    max_speed: float = 0.5  # m/s
    carry_speed_scale: float = 0.5  # slower while holding a fragment
    timeout_s: float = 120.0

    def __post_init__(self) -> None:
        _finite_fields(self)
        for item in dataclasses.fields(self):
            if getattr(self, item.name) <= 0:
                raise ValueError(f"{item.name} must be positive")


@dataclass(frozen=True)
class FSMConfig:
    weights: PairingWeights = field(default_factory=PairingWeights)
    graft: GraftConfig = field(default_factory=GraftConfig)
    nav: NavConfig = field(default_factory=NavConfig)

    wrist_standoff: float = 0.35  # m above bbox top; inside the 0.15-0.5 m wrist camera range
    wrist_depth_range: tuple[float, float] = (0.15, 0.5)
    hull_altitude: float = 2.0  # m above seabed during survey; hull camera 0.5-3.0 m
    hull_depth_range: tuple[float, float] = (0.5, 3.0)
    crop_margin: float = 0.02  # m added to the registry bbox when cropping the wrist cloud

    # Survey lawnmower over [xmin, xmax, ymin, ymax]; only flown when a perceiver is injected.
    survey_bounds: tuple[float, float, float, float] = (0.0, 10.0, 0.0, 10.0)
    survey_swath: float = 2.0  # m between lanes
    seabed_z: float = 0.0

    min_donor_health: float = 0.5  # abstain from using a weak base station rack
    max_attempts_per_recipient: int = 3
    reobserve_attempts: int = 1  # extra wrist captures before giving up on a cluster
    max_perception_failures: int = 3  # consecutive failed survey frames before aborting
    harvest_ik_attempts: int = 2  # tries at taking a fragment before rejecting the rack

    # Return visits. Full recovery needed about a week of contact (Collins et al. 2026).
    revisit_days: tuple[int, ...] = (7, 56)
    recovered_density_pct: float = 80.0  # symbiont density vs healthy tissue at the last visit

    def __post_init__(self) -> None:
        for name, cls in (("weights", PairingWeights), ("graft", GraftConfig), ("nav", NavConfig)):
            if not isinstance(getattr(self, name), cls):
                raise ValueError(f"{name} must be a {cls.__name__}")
        _finite_fields(self)
        _positive_counts(self, "max_attempts_per_recipient", "max_perception_failures", "harvest_ik_attempts")
        if not isinstance(self.reobserve_attempts, int) or self.reobserve_attempts < 0:
            raise ValueError("reobserve_attempts must be a nonnegative integer")
        if self.survey_swath <= 0:
            raise ValueError("survey_swath must be positive")

    def to_dict(self) -> dict[str, Any]:
        return dataclasses.asdict(self)

    @staticmethod
    def from_dict(d: dict[str, Any]) -> "FSMConfig":
        d = dict(d)
        nested = {"weights": PairingWeights, "graft": GraftConfig, "nav": NavConfig}
        for key, cls in nested.items():
            if key in d and isinstance(d[key], dict):
                sub = dict(d[key])
                if "tool_axis" in sub:
                    sub["tool_axis"] = tuple(sub["tool_axis"])
                d[key] = cls(**sub)
        for key in ("wrist_depth_range", "hull_depth_range", "survey_bounds", "revisit_days"):
            if key in d:
                d[key] = tuple(d[key])
        return FSMConfig(**d)
