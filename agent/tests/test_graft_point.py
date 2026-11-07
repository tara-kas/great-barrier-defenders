import numpy as np
import pytest
from scipy.spatial.transform import Rotation

from agent.config import GraftConfig
from agent.graft_point import estimate_normals, select_graft_candidates


def disk(center, radius, spacing=0.005, z=0.0):
    g = np.arange(-radius, radius + 1e-9, spacing)
    gx, gy = np.meshgrid(g, g)
    keep = np.hypot(gx, gy) <= radius
    return np.column_stack([gx[keep] + center[0], gy[keep] + center[1], np.full(keep.sum(), z)])


def tilted_plane(size, spacing, tilt_deg, z0=0.0):
    g = np.arange(-size / 2, size / 2 + 1e-9, spacing)
    gx, gy = np.meshgrid(g, g)
    gz = z0 + np.tan(np.radians(tilt_deg)) * gx
    return np.column_stack([gx.ravel(), gy.ravel(), gz.ravel()])


def test_normals_of_plane_point_up():
    n = estimate_normals(disk((0, 0), 0.05), k=15)
    assert np.allclose(n, [0, 0, 1], atol=1e-6)


def test_flat_upward_patch_on_steep_base_returns_its_centroid():
    # Steep 50 deg slope (fails the 30 deg up filter) with a flat ledge on top.
    base = tilted_plane(0.3, 0.005, 50.0, z0=0.0)
    base = base[base[:, 0] < 0.05]
    ledge_center = np.array([0.1, 0.02, 0.2])
    ledge = disk(ledge_center[:2], 0.04, z=ledge_center[2])
    res = select_graft_candidates(np.vstack([base, ledge]), config=GraftConfig())
    assert res.best is not None
    assert np.allclose(res.best.position, ledge_center, atol=0.01)
    assert res.best.surface_normal[2] > 0.99
    # Gripper approach axis (tool z) is anti-parallel to the normal.
    tool_z = Rotation.from_quat(res.best.orientation_quat).apply([0, 0, 1])
    assert np.dot(tool_z, res.best.surface_normal) == pytest.approx(-1.0, abs=1e-6)


def test_largest_patch_ranked_first():
    big = disk((0.0, 0.0), 0.05, z=0.3)
    small = disk((0.3, 0.0), 0.025, z=0.3)
    res = select_graft_candidates(np.vstack([big, small]))
    assert len(res.candidates) == 2
    assert np.allclose(res.candidates[0].position[:2], (0.0, 0.0), atol=1e-3)
    assert res.candidates[0].patch_size > res.candidates[1].patch_size


def test_vertical_wall_has_no_candidates():
    g = np.arange(0, 0.2, 0.005)
    gy, gz = np.meshgrid(g, g)
    wall = np.column_stack([np.zeros(gy.size), gy.ravel(), gz.ravel()])
    res = select_graft_candidates(wall)
    assert res.candidates == []
    assert "reason" in res.evidence


def test_obstacle_over_patch_blocks_approach():
    patch = disk((0.0, 0.0), 0.04, z=0.2)
    overhang = disk((0.0, 0.0), 0.06, z=0.28)  # neighbouring coral 8 cm above
    clear = select_graft_candidates(patch)
    blocked = select_graft_candidates(patch, obstacles=overhang)
    assert clear.best is not None
    assert blocked.best is None
    assert blocked.evidence["n_clear_approach"] < clear.evidence["n_clear_approach"]


def test_reach_limit():
    patch = disk((0.0, 0.0), 0.04, z=0.2)
    assert select_graft_candidates(patch, reach_center=(0, 0, 0.5)).best is not None
    assert select_graft_candidates(patch, reach_center=(2.0, 0, 0.5)).best is None
