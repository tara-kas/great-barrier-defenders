"""Contract between the mission FSM (agent/fsm.py) and whatever drives the ROV.

eval/mock_robot.py implements this against a synthetic, physics-free scene for
testing. /sim implements it against the real Isaac Sim session. The FSM must
run identically against either.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class Pose:
    position: tuple[float, float, float]
    orientation_quat: tuple[float, float, float, float] = (0.0, 0.0, 0.0, 1.0)


@dataclass(frozen=True)
class RGBDFrame:
    rgb: Any  # HxWx3 array-like
    depth: Any  # HxW array-like, meters
    intrinsics: tuple[float, float, float, float]  # fx, fy, cx, cy
    camera_to_robot: Any  # 4x4 transform, array-like


class RobotInterface(ABC):
    @abstractmethod
    def get_pose(self) -> Pose: ...

    @abstractmethod
    def set_cmd_vel(
        self, linear: tuple[float, float, float], angular: tuple[float, float, float]
    ) -> None: ...

    @abstractmethod
    def lock_base(self) -> None:
        """Kinematically freeze the base so IK solves without floating-base drift."""

    @abstractmethod
    def unlock_base(self) -> None: ...

    @abstractmethod
    def get_hull_rgbd(self) -> RGBDFrame:
        """Downward-looking hull camera, for seabed survey (0.5m - 3.0m)."""

    @abstractmethod
    def get_wrist_rgbd(self) -> RGBDFrame:
        """Wrist-mounted close-range camera, for graft-point selection (0.15m - 0.5m)."""

    @abstractmethod
    def get_uv_frame(self) -> Any:
        """HxWx3 uint8 hull view under UV excitation, pixel-aligned with get_hull_rgbd()."""

    @abstractmethod
    def solve_ik(self, target_pose: Pose) -> bool:
        """Drive the end-effector toward target_pose. Returns whether it was reachable."""

    @abstractmethod
    def attach_fragment(self, cluster_id: str) -> None:
        """Kinematically weld a fragment to the gripper. cluster_id is the base station rack slot."""

    @abstractmethod
    def detach_fragment(self, at_pose: Pose) -> None:
        """Place the carried fragment at at_pose, in contact with the colony there."""
