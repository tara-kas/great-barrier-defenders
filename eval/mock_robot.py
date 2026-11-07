"""MockRobotInterface: physics-free stand-in for the Isaac Sim adapter.

It keeps track of position and attaches or detaches fragments instantly. Hull
and wrist RGB-D frames are rendered from eval/synthetic_scene.py ground-truth
shapes by z-buffered point splatting, so the graft-point selector runs on real
deprojected depth. All frames are synthetic test data.

The FSM's misuse of the interface raises an error rather than being silently
accepted: moving while the base is locked, double attach, or detaching with
nothing held.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, Optional

import numpy as np

from agent.geometry import pose_to_matrix, transform_points
from agent.robot_interface import Pose, RGBDFrame, RobotInterface
from eval.synthetic_scene import ShapeSpec, SyntheticScene
from perception.registry import SemanticMapEntry

# Downward-looking camera: optical z -> robot -z, x -> x, y -> -y.
DOWN_CAMERA = np.array(
    [
        [1.0, 0.0, 0.0, 0.0],
        [0.0, -1.0, 0.0, 0.0],
        [0.0, 0.0, -1.0, 0.0],
        [0.0, 0.0, 0.0, 1.0],
    ]
)

STATUS_RGB = {
    "LIVE": (255, 127, 80),
    "DEAD": (200, 200, 200),
    "BLEACHED": (245, 245, 245),
    "RESTORED": (120, 180, 255),
}
SAND_RGB = (194, 178, 128)


@dataclass(frozen=True)
class CameraModel:
    width: int
    height: int
    fov_deg: float
    depth_range: tuple[float, float]
    sample_spacing: float  # m, surface sampling density for splatting

    @property
    def intrinsics(self) -> tuple[float, float, float, float]:
        f = (self.width / 2.0) / np.tan(np.radians(self.fov_deg) / 2.0)
        return (f, f, (self.width - 1) / 2.0, (self.height - 1) / 2.0)


HULL_CAMERA = CameraModel(64, 64, 70.0, (0.5, 3.0), 0.02)
WRIST_CAMERA = CameraModel(80, 80, 70.0, (0.15, 0.5), 0.004)


def sample_shape(shape: ShapeSpec, spacing: float) -> np.ndarray:
    """World-frame surface points of a ground-truth shape, as seen from above."""
    r = shape.radius
    g = np.arange(-r, r + spacing / 2, spacing)
    gx, gy = np.meshgrid(g, g)
    rr = np.hypot(gx, gy)
    inside = rr <= r
    if shape.kind == "mound":
        z = shape.height * (1.0 - (rr[inside] / r) ** 4)
    elif shape.kind == "pillar":
        z = np.full(inside.sum(), shape.height)
    else:
        raise ValueError(shape.kind)
    pts = np.column_stack([gx[inside] + shape.center[0], gy[inside] + shape.center[1], z])
    if shape.kind == "pillar":
        # Side wall, so the pillar occludes the seabed in oblique views.
        theta = np.arange(0, 2 * np.pi, spacing / r)
        hz = np.arange(0, shape.height, spacing)
        tt, hh = np.meshgrid(theta, hz)
        wall = np.column_stack(
            [shape.center[0] + r * np.cos(tt).ravel(), shape.center[1] + r * np.sin(tt).ravel(), hh.ravel()]
        )
        pts = np.vstack([pts, wall])
    return pts


@dataclass
class MockRobotInterface(RobotInterface):
    scene: SyntheticScene
    start: tuple[float, float, float] = (0.0, 0.0, 2.0)
    reach: float = 0.6
    hull_camera: CameraModel = HULL_CAMERA
    wrist_camera: CameraModel = WRIST_CAMERA

    position: np.ndarray = field(init=False)
    velocity: np.ndarray = field(init=False)
    locked: bool = field(default=False, init=False)
    holding: Optional[str] = field(default=None, init=False)
    placements: list[tuple[str, Pose]] = field(default_factory=list, init=False)
    ik_calls: list[tuple[Pose, bool]] = field(default_factory=list, init=False)
    ik_fail_next: int = field(default=0, init=False)  # perturbation: force N IK failures
    ticks: int = field(default=0, init=False)
    _dislodge_in: Optional[int] = field(default=None, init=False)
    _cache: dict = field(default_factory=dict, init=False)

    def __post_init__(self) -> None:
        self.position = np.asarray(self.start, dtype=float)
        self.velocity = np.zeros(3)

    # ------------------------------------------------------------ RobotInterface

    def get_pose(self) -> Pose:
        return Pose(tuple(float(v) for v in self.position))

    def set_cmd_vel(self, linear, angular) -> None:
        v = np.asarray(linear, dtype=float)
        if self.locked and np.any(v != 0):
            raise RuntimeError("set_cmd_vel with nonzero velocity while base is locked")
        self.velocity = v

    def lock_base(self) -> None:
        self.velocity = np.zeros(3)
        self.locked = True

    def unlock_base(self) -> None:
        self.locked = False

    def get_hull_rgbd(self) -> RGBDFrame:
        return self._render(self.hull_camera)

    def get_wrist_rgbd(self) -> RGBDFrame:
        return self._render(self.wrist_camera)

    def solve_ik(self, target_pose: Pose) -> bool:
        if not self.locked:
            raise RuntimeError("solve_ik called with base unlocked")
        ok = float(np.linalg.norm(np.asarray(target_pose.position) - self.position)) <= self.reach
        if ok and self.ik_fail_next > 0:
            self.ik_fail_next -= 1
            ok = False
        self.ik_calls.append((target_pose, ok))
        return ok

    def attach_fragment(self, cluster_id: str) -> None:
        if self.holding is not None:
            raise RuntimeError(f"attach_fragment while already holding {self.holding}")
        self.holding = cluster_id

    def detach_fragment(self, at_pose: Pose) -> None:
        if self.holding is None:
            raise RuntimeError("detach_fragment with nothing held")
        self.placements.append((self.holding, at_pose))
        self.holding = None
        self._dislodge_in = None

    # --------------------------------------------------- harness / perturbations

    def advance(self, dt: float) -> None:
        """Pass as MissionFSM(wait=...): integrates commanded velocity, no physics."""
        if not self.locked:
            self.position = self.position + self.velocity * dt
        self.ticks += 1
        if self.holding is not None and self._dislodge_in is not None:
            self._dislodge_in -= 1
            if self._dislodge_in <= 0:
                self.holding = None
                self._dislodge_in = None

    def fragment_held(self) -> bool:
        return self.holding is not None

    def schedule_dislodge(self, after_ticks: int) -> None:
        """Perturbation: the carried fragment falls off after N carry ticks."""
        self._dislodge_in = after_ticks

    def perceiver(self, footprint_scale: float = 1.0) -> Callable[[RGBDFrame, Pose], list[SemanticMapEntry]]:
        """Stand-in for the perception branch: returns ground-truth entries of
        clusters inside the hull camera footprint. Synthetic, labelled as such
        by the scene, not a classifier."""

        def detect(frame: RGBDFrame, pose: Pose) -> list[SemanticMapEntry]:
            altitude = pose.position[2]
            half = altitude * np.tan(np.radians(self.hull_camera.fov_deg) / 2.0) * footprint_scale
            out = []
            for e in self.scene.entries:
                if abs(e.position_world[0] - pose.position[0]) <= half and abs(e.position_world[1] - pose.position[1]) <= half:
                    out.append(SemanticMapEntry(**{**e.__dict__}))
            return out

        return detect

    # ------------------------------------------------------------------ render

    def _surface_points(self, spacing: float) -> tuple[np.ndarray, np.ndarray]:
        pts, cols = [], []
        status = {e.cluster_id: e.health_status for e in self.scene.entries}
        for cid, shape in self.scene.shapes.items():
            key = (shape, spacing)
            if key not in self._cache:
                self._cache[key] = sample_shape(shape, spacing)
            p = self._cache[key]
            pts.append(p)
            cols.append(np.tile(STATUS_RGB.get(status.get(cid, "DEAD"), (200, 200, 200)), (len(p), 1)))
        return np.vstack(pts), np.vstack(cols)

    def _render(self, cam: CameraModel) -> RGBDFrame:
        T_world_cam = pose_to_matrix(self.get_pose()) @ DOWN_CAMERA
        fx, fy, cx, cy = cam.intrinsics
        # Seabed patch under the footprint.
        half = (self.position[2] + 0.1) * np.tan(np.radians(cam.fov_deg) / 2.0) * 1.5
        g = np.arange(-half, half, cam.sample_spacing)
        gx, gy = np.meshgrid(g + self.position[0], g + self.position[1])
        sand = np.column_stack([gx.ravel(), gy.ravel(), np.zeros(gx.size)])
        coral, coral_rgb = self._surface_points(cam.sample_spacing)
        world = np.vstack([sand, coral])
        rgb_vals = np.vstack([np.tile(SAND_RGB, (len(sand), 1)), coral_rgb])

        cam_pts = transform_points(np.linalg.inv(T_world_cam), world)
        z = cam_pts[:, 2]
        front = z > 1e-6
        u = np.round(fx * cam_pts[front, 0] / z[front] + cx).astype(int)
        v = np.round(fy * cam_pts[front, 1] / z[front] + cy).astype(int)
        zf, cf = z[front], rgb_vals[front]
        inside = (u >= 0) & (u < cam.width) & (v >= 0) & (v < cam.height)
        u, v, zf, cf = u[inside], v[inside], zf[inside], cf[inside]

        depth = np.full((cam.height, cam.width), np.inf)
        rgb = np.zeros((cam.height, cam.width, 3), dtype=np.uint8)
        # z-buffer: for each pixel keep the nearest point.
        flat = v * cam.width + u
        order = np.lexsort((zf, flat))
        _, first = np.unique(flat[order], return_index=True)
        keep = order[first]
        depth[v[keep], u[keep]] = zf[keep]
        rgb[v[keep], u[keep]] = cf[keep]
        lo, hi = cam.depth_range
        out_of_range = (depth < lo) | (depth > hi)
        depth[out_of_range] = 0.0  # 0 = no return
        rgb[out_of_range] = 0
        return RGBDFrame(rgb=rgb, depth=depth, intrinsics=cam.intrinsics, camera_to_robot=DOWN_CAMERA.copy())
