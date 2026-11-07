"""Frame and point-cloud helpers shared by the FSM and graft-point selector.

Conventions (flag to the team if the sim adapter differs):
- World frame is z-up.
- Quaternions are xyzw, matching `Pose.orientation_quat` and scipy's Rotation.
- Camera points use the OpenCV optical frame (x right, y down, z forward), and
  `RGBDFrame.camera_to_robot` maps that frame into the robot body frame.
- `SemanticMapEntry.position_world` is the centre of the cluster's bounding box.
"""

from __future__ import annotations

from typing import Sequence

import numpy as np
from scipy.spatial.transform import Rotation

from agent.robot_interface import Pose, RGBDFrame
from perception.registry import SemanticMapEntry

UP = np.array([0.0, 0.0, 1.0])


def pose_to_matrix(pose: Pose) -> np.ndarray:
    """4x4 homogeneous transform robot -> world."""
    T = np.eye(4)
    T[:3, :3] = Rotation.from_quat(pose.orientation_quat).as_matrix()
    T[:3, 3] = pose.position
    return T


def transform_points(T: np.ndarray, points: np.ndarray) -> np.ndarray:
    """Apply a 4x4 transform to an Nx3 array."""
    points = np.asarray(points, dtype=float).reshape(-1, 3)
    return points @ T[:3, :3].T + T[:3, 3]


def deproject_depth(
    depth: np.ndarray,
    intrinsics: Sequence[float],
    min_depth: float = 0.0,
    max_depth: float = np.inf,
) -> np.ndarray:
    """Depth image (metres) -> Nx3 camera-frame points. Invalid pixels are dropped."""
    depth = np.asarray(depth, dtype=float)
    fx, fy, cx, cy = intrinsics
    v, u = np.indices(depth.shape)
    valid = np.isfinite(depth) & (depth > min_depth) & (depth <= max_depth)
    d = depth[valid]
    x = (u[valid] - cx) * d / fx
    y = (v[valid] - cy) * d / fy
    return np.column_stack([x, y, d])


def frame_to_world_points(
    frame: RGBDFrame,
    robot_pose: Pose,
    min_depth: float = 0.0,
    max_depth: float = np.inf,
) -> np.ndarray:
    """Deproject an RGB-D frame into world-frame points."""
    cam_pts = deproject_depth(frame.depth, frame.intrinsics, min_depth, max_depth)
    T_world_cam = pose_to_matrix(robot_pose) @ np.asarray(frame.camera_to_robot, dtype=float)
    return transform_points(T_world_cam, cam_pts)


def box_mask(points: np.ndarray, entry: SemanticMapEntry, margin: float = 0.0) -> np.ndarray:
    """Boolean mask of points inside the entry's bounding box (+ margin)."""
    centre = np.asarray(entry.position_world, dtype=float)
    half = np.asarray(entry.bounding_box_extent, dtype=float) / 2.0 + margin
    return np.all(np.abs(np.asarray(points) - centre) <= half, axis=1)


def bbox_top(entry: SemanticMapEntry) -> float:
    return float(entry.position_world[2] + entry.bounding_box_extent[2] / 2.0)


def quat_for_approach(normal: Sequence[float], tool_axis: Sequence[float] = (0.0, 0.0, 1.0)) -> tuple:
    """xyzw quaternion rotating `tool_axis` (end-effector frame) onto -normal,
    so the gripper approaches anti-parallel to the surface normal."""
    target = -np.asarray(normal, dtype=float)
    target /= np.linalg.norm(target)
    axis = np.asarray(tool_axis, dtype=float)
    axis /= np.linalg.norm(axis)
    # Graft normals are near +z, so tool_axis -> target is close to a 180 deg
    # flip, where the minimal rotation's yaw is ill-conditioned. Instead, first
    # point the tool straight down with a fixed flip, then apply the small
    # (well-conditioned) correction from straight down to the target.
    down = -UP
    if np.dot(axis, down) > 1 - 1e-9:
        flip = Rotation.identity()
    elif np.dot(axis, down) < -1 + 1e-9:
        flip = Rotation.from_rotvec(np.pi * np.array([1.0, 0.0, 0.0]))
    else:
        flip, _ = Rotation.align_vectors([down], [axis])
    correction, _ = Rotation.align_vectors([target], [down])
    return tuple(float(q) for q in (correction * flip).as_quat())


def distance(a: Sequence[float], b: Sequence[float]) -> float:
    return float(np.linalg.norm(np.asarray(a, dtype=float) - np.asarray(b, dtype=float)))
