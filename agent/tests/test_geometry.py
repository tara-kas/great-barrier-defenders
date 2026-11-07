import numpy as np
import pytest
from scipy.spatial.transform import Rotation

from agent.config import FSMConfig
from agent.evidence import to_jsonable
from agent.geometry import box_mask, deproject_depth, frame_to_world_points, pose_to_matrix, quat_for_approach
from agent.robot_interface import Pose, RGBDFrame
from perception.registry import SemanticMapEntry


def test_deproject_constant_depth_plane():
    depth = np.full((4, 6), 2.0)
    depth[0, 0] = 0.0  # no return
    pts = deproject_depth(depth, (10.0, 10.0, 2.5, 1.5))
    assert len(pts) == 23
    assert np.allclose(pts[:, 2], 2.0)
    assert pts[:, 0].min() == pytest.approx(-2.5 * 2.0 / 10.0)


def test_frame_to_world_downward_camera():
    down = np.diag([1.0, -1.0, -1.0, 1.0])
    frame = RGBDFrame(rgb=None, depth=np.full((3, 3), 1.0), intrinsics=(1.0, 1.0, 1.0, 1.0), camera_to_robot=down)
    pts = frame_to_world_points(frame, Pose((5.0, 5.0, 3.0)))
    centre = pts[4]  # pixel (1, 1) is on the optical axis
    assert np.allclose(centre, (5.0, 5.0, 2.0))


def test_pose_to_matrix_uses_xyzw():
    q = Rotation.from_euler("z", 90, degrees=True).as_quat()  # xyzw
    T = pose_to_matrix(Pose((1.0, 0.0, 0.0), tuple(q)))
    assert np.allclose(T[:3, :3] @ [1, 0, 0], [0, 1, 0])


@pytest.mark.parametrize("normal", [(0, 0, 1), (0.1, 0.0, 0.99), (0.0, -0.3, 0.95)])
def test_quat_for_approach_points_tool_against_normal(normal):
    n = np.asarray(normal) / np.linalg.norm(normal)
    q = quat_for_approach(n)
    assert np.allclose(Rotation.from_quat(q).apply([0, 0, 1]), -n, atol=1e-9)


def test_box_mask():
    e = SemanticMapEntry("c", "s", "DEAD", 0.0, (0, 0, 0.1), (0.2, 0.2, 0.2))
    pts = np.array([[0, 0, 0.1], [0.11, 0, 0.1], [0.11, 0, 0.1]])
    assert box_mask(pts, e).tolist() == [True, False, False]
    assert box_mask(pts, e, margin=0.02).tolist() == [True, True, True]


def test_config_roundtrip_and_jsonable():
    cfg = FSMConfig()
    d = to_jsonable(cfg.to_dict())
    d["weights"]["w3"] = 3.0
    patched = FSMConfig.from_dict(d)
    assert patched.weights.w3 == 3.0
    assert patched.graft == cfg.graft
