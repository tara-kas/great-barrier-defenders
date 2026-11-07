"""PCA graft-point selector (pure, numpy + scipy).

Input is a world-frame (z-up) point cloud of one coral structure, cropped from
the wrist RGB-D frame, plus the points around it (neighbouring coral, seabed)
that the gripper must not hit.

1. k-NN (k=15) surface normals: smallest eigenvector of the local covariance.
2. Keep upward-facing points (n . z > cos 30 deg) in the upper 50th percentile of height.
3. Reject points outside manipulator reach or whose approach cylinder along
   the normal contains any other point.
4. Candidates are contiguous valid patches, largest first. Each gives a
   centroid, a mean normal, and a gripper orientation anti-parallel to that normal.

The same selector picks harvest points on LIVE donors, with a different config.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional, Sequence

import numpy as np
from scipy.sparse import coo_matrix
from scipy.sparse.csgraph import connected_components
from scipy.spatial import cKDTree

from agent.config import GraftConfig
from agent.geometry import UP, quat_for_approach
from perception.registry import GraftPose


@dataclass(frozen=True)
class GraftCandidate:
    position: tuple[float, float, float]
    orientation_quat: tuple[float, float, float, float]
    surface_normal: tuple[float, float, float]
    patch_size: int
    upward_dot: float

    def to_graft_pose(self) -> GraftPose:
        return GraftPose(self.position, self.orientation_quat, self.surface_normal)


@dataclass
class GraftResult:
    candidates: list[GraftCandidate]
    evidence: dict = field(default_factory=dict)

    @property
    def best(self) -> Optional[GraftCandidate]:
        return self.candidates[0] if self.candidates else None


def estimate_normals(points: np.ndarray, k: int = 15, tree: Optional[cKDTree] = None) -> np.ndarray:
    """Per-point unit normals from k-NN covariance, oriented to +z."""
    points = np.asarray(points, dtype=float)
    n = len(points)
    if n < 3:
        return np.tile(UP, (n, 1))
    k = min(k, n)
    tree = tree or cKDTree(points)
    _, idx = tree.query(points, k=k)
    nbrs = points[idx]  # (n, k, 3)
    centred = nbrs - nbrs.mean(axis=1, keepdims=True)
    cov = np.einsum("nki,nkj->nij", centred, centred) / k
    _, vecs = np.linalg.eigh(cov)  # ascending eigenvalues
    normals = vecs[:, :, 0]
    normals[normals[:, 2] < 0] *= -1.0
    return normals


def _approach_clear(
    candidates: np.ndarray,
    normals: np.ndarray,
    others: np.ndarray,
    cfg: GraftConfig,
) -> np.ndarray:
    """True where the cylinder (radius r, from clearance to length L along the
    normal) contains no point of `others`."""
    clear = np.ones(len(candidates), dtype=bool)
    if len(others) == 0 or len(candidates) == 0:
        return clear
    tree = cKDTree(others)
    half = cfg.approach_length / 2.0
    ball_r = float(np.hypot(half, cfg.approach_radius))
    mids = candidates + normals * half
    hits = tree.query_ball_point(mids, ball_r)
    for i, nbr in enumerate(hits):
        if not nbr:
            continue
        rel = others[nbr] - candidates[i]
        t = rel @ normals[i]
        radial = np.linalg.norm(rel - np.outer(t, normals[i]), axis=1)
        inside = (t > cfg.approach_clearance) & (t < cfg.approach_length) & (radial < cfg.approach_radius)
        if inside.any():
            clear[i] = False
    return clear


def select_graft_candidates(
    points: np.ndarray,
    *,
    obstacles: Optional[np.ndarray] = None,
    reach_center: Optional[Sequence[float]] = None,
    config: GraftConfig = GraftConfig(),
) -> GraftResult:
    """Ranked graft (or harvest) candidates on `points`, with per-stage evidence."""
    points = np.asarray(points, dtype=float).reshape(-1, 3)
    obstacles = np.empty((0, 3)) if obstacles is None else np.asarray(obstacles, dtype=float).reshape(-1, 3)
    ev: dict = {"n_points": int(len(points)), "n_obstacle_points": int(len(obstacles))}
    if len(points) < max(config.k_neighbors, config.min_patch_points):
        ev["reason"] = "too few points on structure"
        return GraftResult([], ev)

    tree = cKDTree(points)
    normals = estimate_normals(points, config.k_neighbors, tree)
    up_dot = normals @ UP

    upward = up_dot > config.min_up_dot
    z_cut = float(np.percentile(points[:, 2], config.height_percentile))
    high = points[:, 2] >= z_cut
    valid = upward & high
    ev.update(n_upward=int(upward.sum()), height_cut_z=z_cut, n_upward_and_high=int(valid.sum()))

    if reach_center is not None:
        in_reach = np.linalg.norm(points - np.asarray(reach_center, dtype=float), axis=1) <= config.reach_radius
        valid &= in_reach
    ev["n_in_reach"] = int(valid.sum())

    idx = np.flatnonzero(valid)
    # Anything not on the structure, plus the structure's own points, can block the approach.
    others = np.vstack([points, obstacles])
    clear = _approach_clear(points[idx], normals[idx], others, config)
    idx = idx[clear]
    ev["n_clear_approach"] = int(len(idx))

    if len(idx) < config.min_patch_points:
        ev["reason"] = "no upward, reachable, unobstructed patch large enough"
        ev["patch_sizes"] = []
        return GraftResult([], ev)

    sub = points[idx]
    pairs = cKDTree(sub).query_pairs(config.patch_connect_radius, output_type="ndarray")
    graph = coo_matrix((np.ones(len(pairs)), (pairs[:, 0], pairs[:, 1])), shape=(len(sub), len(sub)))
    n_comp, labels = connected_components(graph, directed=False)
    sizes = np.bincount(labels, minlength=n_comp)
    order = np.argsort(-sizes, kind="stable")
    ev["patch_sizes"] = [int(s) for s in sizes[order][:10]]

    candidates = []
    for comp in order:
        if sizes[comp] < config.min_patch_points or len(candidates) >= config.max_candidates:
            break
        members = idx[labels == comp]
        centroid = points[members].mean(axis=0)
        normal = normals[members].mean(axis=0)
        normal /= np.linalg.norm(normal)
        candidates.append(
            GraftCandidate(
                position=tuple(float(v) for v in centroid),
                orientation_quat=quat_for_approach(normal, config.tool_axis),
                surface_normal=tuple(float(v) for v in normal),
                patch_size=int(sizes[comp]),
                upward_dot=float(normal @ UP),
            )
        )
    if not candidates:
        ev["reason"] = "no contiguous patch reaches min_patch_points"
    return GraftResult(candidates, ev)
