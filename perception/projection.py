"""Pixel + depth -> world-frame projection (spec PDF section 5.2).

    P_world = T_world_from_robot · T_robot_from_cam · (d · K⁻¹ · [u, v, 1]ᵀ)

Conventions (the /sim adapter must match these when it builds an RGBDFrame):
- Camera frame is the OpenCV optical frame: +x right, +y down, +z forward.
  Isaac Sim's USD camera looks down -z with +y up, so `camera_to_robot` must
  include that axis flip.
- `depth` is z-depth along the optical axis (Isaac Sim's
  `distance_to_image_plane` annotator), in metres, not range along the ray.
- `Pose.orientation_quat` is (x, y, z, w) and maps robot frame -> world frame.
- Non-finite or non-positive depth is treated as "no return".
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from agent.robot_interface import Pose, RGBDFrame


def intrinsics_matrix(intrinsics: tuple[float, float, float, float]) -> np.ndarray:
    fx, fy, cx, cy = intrinsics
    return np.array([[fx, 0.0, cx], [0.0, fy, cy], [0.0, 0.0, 1.0]])


def quat_to_rotmat(q: tuple[float, float, float, float]) -> np.ndarray:
    x, y, z, w = q
    n = np.sqrt(x * x + y * y + z * z + w * w)
    if n == 0:
        raise ValueError("zero-norm quaternion")
    x, y, z, w = x / n, y / n, z / n, w / n
    return np.array(
        [
            [1 - 2 * (y * y + z * z), 2 * (x * y - z * w), 2 * (x * z + y * w)],
            [2 * (x * y + z * w), 1 - 2 * (x * x + z * z), 2 * (y * z - x * w)],
            [2 * (x * z - y * w), 2 * (y * z + x * w), 1 - 2 * (x * x + y * y)],
        ]
    )


def pose_to_matrix(pose: Pose) -> np.ndarray:
    """4x4 transform taking robot-frame points to world frame."""
    T = np.eye(4)
    T[:3, :3] = quat_to_rotmat(pose.orientation_quat)
    T[:3, 3] = pose.position
    return T


def camera_to_world_matrix(frame: RGBDFrame, pose: Pose) -> np.ndarray:
    return pose_to_matrix(pose) @ np.asarray(frame.camera_to_robot, dtype=float)


def pixels_to_camera(u: np.ndarray, v: np.ndarray, d: np.ndarray, intrinsics) -> np.ndarray:
    """Back-project pixels (arrays of equal shape) to Nx3 camera-frame points."""
    fx, fy, cx, cy = intrinsics
    u, v, d = (np.asarray(a, dtype=float).ravel() for a in (u, v, d))
    return np.stack([(u - cx) * d / fx, (v - cy) * d / fy, d], axis=1)


def transform_points(T: np.ndarray, pts: np.ndarray) -> np.ndarray:
    return pts @ T[:3, :3].T + T[:3, 3]


def pixel_to_world(u: float, v: float, d: float, frame: RGBDFrame, pose: Pose) -> tuple[float, float, float]:
    """Project a single pixel with known depth to a world-frame point."""
    if not np.isfinite(d) or d <= 0:
        raise ValueError(f"invalid depth {d!r} at pixel ({u}, {v})")
    p_cam = pixels_to_camera(np.array([u]), np.array([v]), np.array([d]), frame.intrinsics)
    p = transform_points(camera_to_world_matrix(frame, pose), p_cam)[0]
    return (float(p[0]), float(p[1]), float(p[2]))


@dataclass(frozen=True)
class BoxProjection:
    position_world: tuple[float, float, float]
    bounding_box_extent: tuple[float, float, float]  # full size along world x, y, z (m)
    median_depth: float
    valid_fraction: float  # share of sampled pixels with a usable depth return


def project_box(
    frame: RGBDFrame,
    pose: Pose,
    box_xyxy: tuple[int, int, int, int],
    max_samples: int = 4000,
    lo_pct: float = 5.0,
    hi_pct: float = 95.0,
) -> BoxProjection:
    """Back-project every valid depth pixel inside a pixel box to world frame.

    Position is the per-axis median of the points; extent is the 5th-95th
    percentile span per world axis (robust to edge pixels that hit the seabed
    behind the coral).
    """
    depth = np.asarray(frame.depth, dtype=float)
    h, w = depth.shape[:2]
    x0, y0, x1, y1 = box_xyxy
    x0, x1 = max(0, int(x0)), min(w, int(x1))
    y0, y1 = max(0, int(y0)), min(h, int(y1))
    if x1 <= x0 or y1 <= y0:
        raise ValueError(f"empty box {box_xyxy} for {w}x{h} frame")

    vv, uu = np.mgrid[y0:y1, x0:x1]
    dd = depth[y0:y1, x0:x1]
    uu, vv, dd = uu.ravel(), vv.ravel(), dd.ravel()
    total = dd.size
    ok = np.isfinite(dd) & (dd > 0)
    uu, vv, dd = uu[ok], vv[ok], dd[ok]
    if dd.size == 0:
        raise ValueError(f"no valid depth inside box {box_xyxy}")
    if dd.size > max_samples:
        idx = np.linspace(0, dd.size - 1, max_samples).astype(int)
        uu, vv, dd = uu[idx], vv[idx], dd[idx]

    # Pixel centres are at +0.5.
    pts_cam = pixels_to_camera(uu + 0.5, vv + 0.5, dd, frame.intrinsics)
    pts = transform_points(camera_to_world_matrix(frame, pose), pts_cam)
    centre = np.median(pts, axis=0)
    extent = np.percentile(pts, hi_pct, axis=0) - np.percentile(pts, lo_pct, axis=0)
    return BoxProjection(
        position_world=tuple(float(c) for c in centre),
        bounding_box_extent=tuple(float(e) for e in extent),
        median_depth=float(np.median(dd)),
        valid_fraction=float(ok.sum() / total),
    )
