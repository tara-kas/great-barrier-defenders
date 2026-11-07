"""The Moore Reef scenario: a 10 x 10 m patch of Great Barrier Reef after a heat stress event.

Defines the reef, the base station stock and the labels, and renders aligned
RGB, depth and UV frames from any pose. eval/generate_moore_reef.py writes the
dataset in data/moore_reef/. Everything is deterministic for a given SEED.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

import numpy as np
from PIL import Image

from agent.base_station import BaseStation, Rack
from agent.robot_interface import Pose, RGBDFrame
from eval.mock_robot import DOWN_CAMERA, CameraModel, MockRobotInterface
from eval.synthetic_scene import ShapeSpec, SyntheticScene, _entry_for
from perception.genet import BANDS, UV_BACKGROUND, GenetRecord, match_genet
from perception.projection import pose_to_matrix
from perception.registry import SemanticMapEntry

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data" / "moore_reef"
TEXTURES = DATA_DIR / "textures"

SEED = 2026
BOUNDS = (0.0, 10.0, 0.0, 10.0)
SITE_DEPTH_M = 8.0  # depth of the seabed datum, z = 0 in the local frame
BASE_STATION = (-1.5, 5.0, 0.0)  # just outside the survey area
FRAME_CAMERA = CameraModel(512, 512, 70.0, (0.5, 3.0), 0.02)
MARCH_STEP_M = 0.01

# Emission share in the cyan, green and red bands, summing to 1.
GENETS: dict[str, dict[str, Any]] = {
    "PD-01": {"species_class": "pocillopora", "signature": (0.10, 0.70, 0.20), "stock": 6},
    "PD-02": {"species_class": "pocillopora", "signature": (0.12, 0.30, 0.58), "stock": 4},
    "AB-01": {"species_class": "acropora_branching", "signature": (0.55, 0.35, 0.10), "stock": 5},
    "AB-02": {"species_class": "acropora_branching", "signature": (0.18, 0.62, 0.20), "stock": 0},
    "AT-01": {"species_class": "acropora_table", "signature": (0.40, 0.45, 0.15), "stock": 3},
    "MM-01": {"species_class": "massive_meandering", "signature": (0.08, 0.22, 0.70), "stock": 3},
    "MM-02": {"species_class": "massive_meandering", "signature": (0.30, 0.30, 0.40), "stock": 0},
}

CONTACT_DAYS_REQUIRED = 7
REVISIT_DAYS = (7, 56)

# (genet or species for DEAD, status, role). Roles drive the expected action.
CLUSTER_PLAN: list[tuple[str, str, str]] = [
    ("PD-01", "BLEACHED", "treat"), ("PD-01", "BLEACHED", "treat"),
    ("PD-02", "BLEACHED", "treat"), ("PD-02", "BLEACHED", "treat"),
    ("AB-01", "BLEACHED", "treat"), ("AB-01", "BLEACHED", "treat"),
    ("AT-01", "BLEACHED", "treat"), ("MM-01", "BLEACHED", "treat"),
    ("AB-02", "BLEACHED", "no_stock"), ("MM-02", "BLEACHED", "no_stock"),
    ("PD-01", "BLEACHED", "ambiguous"), ("PD-02", "BLEACHED", "ambiguous"),
    ("pocillopora", "DEAD", "dead"), ("acropora_branching", "DEAD", "dead"),
    ("acropora_table", "DEAD", "dead"), ("massive_meandering", "DEAD", "dead"),
    ("PD-01", "LIVE", "healthy"), ("AB-01", "LIVE", "healthy"),
    ("AT-01", "LIVE", "healthy"), ("MM-02", "LIVE", "healthy"),
]

EXPECTED_ACTION = {
    "treat": "TREAT",
    "no_stock": "SKIP_NO_MATCHING_GENET",
    "ambiguous": "ABSTAIN_UV_MATCH_UNCERTAIN",
    "dead": "SKIP_DEAD",
    "healthy": "LEAVE",
}
HEALTH_SCORE = {"LIVE": (0.72, 0.97), "BLEACHED": (0.28, 0.6), "DEAD": (0.03, 0.2)}
UV_INTENSITY = {"LIVE": 1.0, "BLEACHED": 1.5, "DEAD": 0.08}  # bleached tissue glows brighter
HEIGHT_RANGE = {
    "acropora_table": (0.14, 0.2),
    "pocillopora": (0.2, 0.3),
    "acropora_branching": (0.22, 0.32),
    "massive_meandering": (0.22, 0.32),
}


@dataclass
class ReefCluster:
    cluster_id: str
    species_class: str
    health_status: str
    health_score: float
    genet_id: Optional[str]
    role: str
    shape: ShapeSpec
    uv_signature: Optional[tuple[float, float, float]]
    uv_intensity: float
    rotation_rad: float

    @property
    def expected_action(self) -> str:
        return EXPECTED_ACTION[self.role]

    def label(self) -> dict[str, Any]:
        x, y = self.shape.center
        return {
            "cluster_id": self.cluster_id,
            "species_class": self.species_class,
            "health_status": self.health_status,
            "health_score": self.health_score,
            "genet_id": self.genet_id,
            "position_world": [round(x, 4), round(y, 4), round(self.shape.height / 2, 4)],
            "bounding_box_extent": [round(v, 4) for v in self.shape.bbox_extent()],
            "depth_m": round(SITE_DEPTH_M - self.shape.height, 2),
            "uv_signature": list(self.uv_signature) if self.uv_signature else None,
            "uv_intensity": self.uv_intensity,
            "expected_action": self.expected_action,
        }


@dataclass
class MooreReef:
    clusters: list[ReefCluster]
    scene: SyntheticScene = field(init=False)

    def __post_init__(self) -> None:
        shapes = {c.cluster_id: c.shape for c in self.clusters}
        entries = [_registry_entry(c) for c in self.clusters]
        self.scene = SyntheticScene(entries, shapes, BOUNDS, SEED)

    def cluster(self, cluster_id: str) -> ReefCluster:
        return next(c for c in self.clusters if c.cluster_id == cluster_id)


def genet_library() -> list[GenetRecord]:
    return [GenetRecord(k, g["species_class"], g["signature"]) for k, g in GENETS.items()]


def _registry_entry(c: ReefCluster) -> SemanticMapEntry:
    """What a survey should conclude: the genet comes from the UV match, not the label."""
    entry = _entry_for(c.cluster_id, c.species_class, c.health_status, c.health_score, c.shape)
    if c.health_status != "BLEACHED":
        return entry
    entry.genet_id = match_genet(c.species_class, c.uv_signature, genet_library()).genet_id
    entry.uv_signature = c.uv_signature
    return entry


def _normalise(values: np.ndarray) -> tuple[float, float, float]:
    clipped = np.clip(values, 0.001, None)
    return tuple(round(float(v), 4) for v in clipped / clipped.sum())


def _centers(rng: np.random.Generator, count: int) -> list[tuple[float, float]]:
    xmin, xmax, ymin, ymax = BOUNDS
    centers: list[tuple[float, float]] = []
    while len(centers) < count:
        c = (float(rng.uniform(xmin + 0.7, xmax - 0.7)), float(rng.uniform(ymin + 0.7, ymax - 0.7)))
        if all(np.hypot(c[0] - o[0], c[1] - o[1]) >= 1.0 for o in centers):
            centers.append(c)
    return centers


def _observed_signature(rng, genet_id: str, role: str) -> tuple[float, float, float]:
    signature = np.array(GENETS[genet_id]["signature"])
    if role == "ambiguous":  # reads halfway between the two Pocillopora genets
        other = "PD-02" if genet_id == "PD-01" else "PD-01"
        signature = 0.5 * signature + 0.5 * np.array(GENETS[other]["signature"])
    return _normalise(signature + rng.normal(0.0, 0.012, 3))


def build_reef(seed: int = SEED) -> MooreReef:
    rng = np.random.default_rng(seed)
    plan = [CLUSTER_PLAN[i] for i in rng.permutation(len(CLUSTER_PLAN))]
    clusters = []
    for index, (center, (source, status, role)) in enumerate(zip(_centers(rng, len(plan)), plan), start=1):
        genet_id = source if source in GENETS else None
        species = GENETS[source]["species_class"] if genet_id else source
        shape = ShapeSpec("mound", center, float(rng.uniform(0.2, 0.32)), float(rng.uniform(*HEIGHT_RANGE[species])))
        clusters.append(ReefCluster(
            cluster_id=f"MR-{index:03d}",
            species_class=species,
            health_status=status,
            health_score=round(float(rng.uniform(*HEALTH_SCORE[status])), 3),
            genet_id=genet_id,
            role=role,
            shape=shape,
            uv_signature=_observed_signature(rng, genet_id, role) if genet_id else None,
            uv_intensity=UV_INTENSITY[status],
            rotation_rad=float(rng.uniform(0, 2 * np.pi)),
        ))
    return MooreReef(clusters)


def base_station_stock() -> dict[str, Any]:
    slots = [
        {
            "slot": f"R{index:02d}",
            "genet_id": genet_id,
            "species_class": genet["species_class"],
            "fragments_available": genet["stock"],
            "health_status": "LIVE",
            "health_score": 0.95,
            "uv_signature": list(genet["signature"]),
        }
        for index, (genet_id, genet) in enumerate(GENETS.items(), start=1)
        if genet["stock"] > 0
    ]
    return {"position_world": list(BASE_STATION), "racks": slots}


def moore_station() -> BaseStation:
    stock = base_station_stock()
    fields = ("slot", "genet_id", "species_class", "fragments_available", "health_score")
    return BaseStation(tuple(stock["position_world"]), [Rack(**{k: r[k] for k in fields}) for r in stock["racks"]])


def recovery_timeline(reef: MooreReef) -> list[dict[str, Any]]:
    """Follow-up results for treated colonies. One loses contact and one is overgrown."""
    treated = [c for c in reef.clusters if c.role == "treat"]
    rng = np.random.default_rng(SEED + 1)
    failures = {treated[1].cluster_id: "contact_lost", treated[-2].cluster_id: "algal_overgrowth"}
    rows = []
    for c in treated:
        failure = failures.get(c.cluster_id)
        day7 = round(float(rng.uniform(0.35, 0.55)), 2)
        rows.append({
            "cluster_id": c.cluster_id,
            "genet_id": c.genet_id,
            "observations": [
                {"day": 0, "status": "TREATED", "symbiont_density_pct_of_healthy": 0, "contact_maintained": True},
                {
                    "day": REVISIT_DAYS[0],
                    "status": "TREATED",
                    "symbiont_density_pct_of_healthy": 2 if failure == "contact_lost" else round(day7 * 100),
                    "contact_maintained": failure != "contact_lost",
                },
                {
                    "day": REVISIT_DAYS[1],
                    "status": "NOT_RECOVERED" if failure else "RECOVERED",
                    "symbiont_density_pct_of_healthy": 5 if failure else round(float(rng.uniform(88, 100))),
                    "contact_maintained": failure != "contact_lost",
                },
            ],
            "outcome": "NOT_RECOVERED" if failure else "RECOVERED",
            "failure_reason": failure,
        })
    return rows


class TextureSet:
    """Colony and seabed tiles, as float RGB arrays."""

    def __init__(self, directory: Path = TEXTURES) -> None:
        self.directory = directory
        self._cache: dict[str, np.ndarray] = {}

    def get(self, name: str) -> np.ndarray:
        if name not in self._cache:
            with Image.open(self.directory / f"{name}.jpg") as image:
                self._cache[name] = np.asarray(image.convert("RGB"), dtype=np.float32) / 255.0
        return self._cache[name]

    def seabed(self) -> np.ndarray:
        if "seabed_wrapped" not in self._cache:
            self._cache["seabed_wrapped"] = seamless(self.get("seabed")).astype(np.float32)
        return self._cache["seabed_wrapped"]

    def colony(self, cluster: ReefCluster) -> np.ndarray:
        return self.get(f"{cluster.species_class}_{cluster.health_status.lower()}")


def _sample(texture: np.ndarray, u: np.ndarray, v: np.ndarray) -> np.ndarray:
    height, width = texture.shape[:2]
    rows = np.clip((v * (height - 1)).astype(int), 0, height - 1)
    cols = np.clip((u * (width - 1)).astype(int), 0, width - 1)
    return texture[rows, cols]


def _wrap_axis(tile: np.ndarray, axis: int) -> np.ndarray:
    """Hide the tile's edge along one axis behind a half-offset copy of itself."""
    size = tile.shape[axis]
    ramp = np.clip(np.minimum(np.arange(size), size - 1 - np.arange(size)) / (0.2 * size), 0.0, 1.0)
    weight = ramp.reshape((-1, 1, 1) if axis == 0 else (1, -1, 1))
    return weight * tile + (1.0 - weight) * np.roll(tile, size // 2, axis=axis)


def seamless(tile: np.ndarray) -> np.ndarray:
    """A tile that repeats with no visible edge. One axis at a time, so no seam survives."""
    return _wrap_axis(_wrap_axis(tile, 1), 0)


def _radial(shape: ShapeSpec, origin: np.ndarray, rays: np.ndarray, z: float) -> np.ndarray:
    t = (z - origin[2]) / rays[:, 2]
    return np.hypot(origin[0] + t * rays[:, 0] - shape.center[0], origin[1] + t * rays[:, 1] - shape.center[1]) / shape.radius


def _march(shape: ShapeSpec, origin: np.ndarray, rays: np.ndarray, surface_z: np.ndarray, index: np.ndarray, i: int) -> None:
    """Find where rays first meet this mound, stepping down from its top."""
    flat_rays = rays.reshape(-1, 3)
    near = np.minimum(_radial(shape, origin, flat_rays, 0.0), _radial(shape, origin, flat_rays, shape.height)) <= 1.2
    pixels = np.flatnonzero(near)  # only rays that pass close enough to touch this mound
    if pixels.size == 0:
        return
    candidates, flat_z, flat_index = flat_rays[pixels], surface_z.reshape(-1), index.reshape(-1)
    for z in np.arange(shape.height, -MARCH_STEP_M, -MARCH_STEP_M):
        radial = _radial(shape, origin, candidates, z)
        hit = (radial <= 1.0) & (shape.height * (1.0 - radial**4) >= z) & (z > flat_z[pixels])
        flat_z[pixels[hit]] = max(z, 1e-6)
        flat_index[pixels[hit]] = i


@dataclass
class RenderedView:
    rgb: np.ndarray  # HxWx3 uint8
    uv: np.ndarray  # HxWx3 uint8, as seen under UV excitation
    depth: np.ndarray  # HxW float metres, 0 = no return
    cluster_index: np.ndarray  # HxW int, -1 = seabed
    intrinsics: tuple[float, float, float, float]


def render_view(reef: MooreReef, textures: TextureSet, pose: Pose, camera: CameraModel = FRAME_CAMERA) -> RenderedView:
    """Ray-cast the height field, so RGB, UV and depth line up pixel for pixel."""
    fx, fy, cx, cy = camera.intrinsics
    u, v = np.meshgrid(np.arange(camera.width, dtype=float), np.arange(camera.height, dtype=float))
    rays_cam = np.stack([(u - cx) / fx, (v - cy) / fy, np.ones_like(u)], axis=-1)
    world_from_cam = pose_to_matrix(pose) @ DOWN_CAMERA
    rotation, origin = world_from_cam[:3, :3], world_from_cam[:3, 3]
    rays = rays_cam @ rotation.T

    surface_z = np.zeros_like(u)
    index = np.full(u.shape, -1, dtype=int)
    for i, cluster in enumerate(reef.clusters):
        _march(cluster.shape, origin, rays, surface_z, index, i)
    t = (surface_z - origin[2]) / rays[..., 2]
    x, y = origin[0] + t * rays[..., 0], origin[1] + t * rays[..., 1]
    depth = t.copy()  # rays have unit camera-z, so t is camera-frame depth

    seabed = textures.seabed()
    tile_m = 4.0
    rgb = _sample(seabed, (x / tile_m) % 1.0, (y / tile_m) % 1.0).copy()
    uv = np.broadcast_to(UV_BACKGROUND.astype(np.float32), rgb.shape).copy()
    bands = BANDS.astype(np.float32)

    for i, cluster in enumerate(reef.clusters):
        mask = index == i
        if not mask.any():
            continue
        shape = cluster.shape
        dx = (x[mask] - shape.center[0]) / shape.radius
        dy = (y[mask] - shape.center[1]) / shape.radius
        cos, sin = np.cos(cluster.rotation_rad), np.sin(cluster.rotation_rad)
        tex_u = 0.5 + 0.5 * (cos * dx - sin * dy) * 0.92
        tex_v = 0.5 + 0.5 * (sin * dx + cos * dy) * 0.92
        colour = _sample(textures.colony(cluster), tex_u, tex_v)
        alpha = np.clip((1.0 - np.hypot(dx, dy)) / 0.14, 0.0, 1.0)[:, None]
        rgb[mask] = alpha * colour + (1.0 - alpha) * rgb[mask]

        relief = colour.mean(axis=1, keepdims=True)
        if cluster.uv_signature is None:  # turf algae on dead skeleton gives a faint red
            glow = np.array([0.3, 0.05, 0.03], dtype=np.float32) * cluster.uv_intensity * 3.0 * relief
        else:
            mix = np.array(cluster.uv_signature, dtype=np.float32) @ bands
            glow = mix * cluster.uv_intensity * (0.2 + 0.4 * relief)  # kept below sensor saturation
        uv[mask] = alpha * np.clip(glow, 0.0, 1.0) + (1.0 - alpha) * uv[mask]

    return RenderedView(
        rgb=_finish_rgb(rgb, pose),
        uv=(np.clip(uv, 0.0, 1.0) * 255).astype(np.uint8),
        depth=np.where((depth >= camera.depth_range[0]) & (depth <= camera.depth_range[1]), depth, 0.0),
        cluster_index=index,
        intrinsics=camera.intrinsics,
    )


def _finish_rgb(rgb: np.ndarray, pose: Pose) -> np.ndarray:
    """Water column colour cast, vignette and sensor noise."""
    height, width = rgb.shape[:2]
    yy, xx = np.mgrid[0:height, 0:width]
    radial = np.hypot((xx - width / 2) / width, (yy - height / 2) / height)
    vignette = (1.0 - 0.55 * radial**2)[..., None]
    cast = np.array([0.82, 0.96, 1.0], dtype=np.float32)
    seed = int(abs(pose.position[0]) * 1000 + abs(pose.position[1]) * 7)
    noise = np.random.default_rng(seed).normal(0.0, 0.008, rgb.shape).astype(np.float32)
    return (np.clip(rgb * cast * vignette + noise, 0.0, 1.0) * 255).astype(np.uint8)


class MooreReefRobot(MockRobotInterface):
    """The mock robot, with hull frames rendered from the Moore Reef textures."""

    def __init__(self, reef: Optional[MooreReef] = None, textures: Optional[TextureSet] = None, **kwargs: Any) -> None:
        self.reef = reef or build_reef()
        self.textures = textures or TextureSet()
        self._last_view: Optional[tuple[Pose, RenderedView]] = None
        super().__init__(self.reef.scene, **kwargs)

    def view(self) -> RenderedView:
        """The render from the current pose. The scene is static, so repeat poses reuse it."""
        pose = self.get_pose()
        if self._last_view is None or self._last_view[0] != pose:
            self._last_view = (pose, render_view(self.reef, self.textures, pose))
        return self._last_view[1]

    def get_hull_rgbd(self) -> RGBDFrame:
        view = self.view()
        return RGBDFrame(rgb=view.rgb, depth=view.depth, intrinsics=view.intrinsics, camera_to_robot=DOWN_CAMERA)

    def get_uv_frame(self) -> np.ndarray:
        return self.view().uv

    def observe_recovery(self, entry: SemanticMapEntry, day: int) -> dict[str, Any]:
        """The scenario's follow-up reading for the colony at this registry entry."""
        x, y = entry.position_world[:2]
        cluster = min(self.reef.clusters, key=lambda c: np.hypot(c.shape.center[0] - x, c.shape.center[1] - y))
        record = next(r for r in recovery_timeline(self.reef) if r["cluster_id"] == cluster.cluster_id)
        return next(o for o in record["observations"] if o["day"] == day)
