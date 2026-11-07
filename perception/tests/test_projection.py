import numpy as np
import pytest
from scipy.spatial.transform import Rotation

from agent.robot_interface import Pose, RGBDFrame
from perception.projection import pixel_to_world, project_box, quat_to_rotmat
from perception.tests.fakes import flat_frame


def identity_frame(f=100.0, cx=50.0, cy=40.0):
    return RGBDFrame(rgb=None, depth=None, intrinsics=(f, f, cx, cy), camera_to_robot=np.eye(4))


def test_principal_point_projects_onto_optical_axis():
    p = pixel_to_world(50, 40, 1.0, identity_frame(), Pose((0, 0, 0)))
    assert p == pytest.approx((0, 0, 1))


def test_offset_pixel_scales_with_depth():
    p = pixel_to_world(150, 40, 2.0, identity_frame(), Pose((0, 0, 0)))
    assert p == pytest.approx((2, 0, 2))


def test_robot_pose_rotation_and_translation():
    yaw90 = (0, 0, np.sin(np.pi / 4), np.cos(np.pi / 4))
    p = pixel_to_world(150, 40, 1.0, identity_frame(), Pose((1, 2, 3), yaw90))
    assert p == pytest.approx((1, 3, 4))


@pytest.mark.parametrize("q", [(0, 0, 0, 1), (0.1, -0.3, 0.5, 0.8), (1, 0, 0, 0)])
def test_quat_matches_scipy(q):
    assert quat_to_rotmat(q) == pytest.approx(Rotation.from_quat(q).as_matrix())


def test_invalid_depth_rejected():
    with pytest.raises(ValueError):
        pixel_to_world(0, 0, float("nan"), identity_frame(), Pose((0, 0, 0)))
    with pytest.raises(ValueError):
        pixel_to_world(0, 0, 0.0, identity_frame(), Pose((0, 0, 0)))


def test_downward_camera_box_lands_on_seabed():
    frame = flat_frame(w=200, h=100, depth=2.0, f=100.0)
    proj = project_box(frame, Pose((5, 5, 2)), (0, 0, 200, 100))
    assert proj.position_world == pytest.approx((5, 5, 0), abs=0.02)
    # Full frame spans 4 m x 2 m on the seabed; extent is the 5-95 percentile span.
    assert proj.bounding_box_extent[0] == pytest.approx(3.6, abs=0.05)
    assert proj.bounding_box_extent[1] == pytest.approx(1.8, abs=0.05)
    assert proj.bounding_box_extent[2] == pytest.approx(0, abs=1e-9)
    assert proj.median_depth == 2.0 and proj.valid_fraction == 1.0


def test_box_ignores_invalid_depth_and_reports_fraction():
    frame = flat_frame()
    frame.depth[:, :100] = np.nan
    proj = project_box(frame, Pose((0, 0, 2)), (0, 0, 200, 100))
    assert proj.valid_fraction == pytest.approx(0.5)
    assert proj.position_world[0] > 0  # only the right half contributed


def test_box_with_no_depth_raises():
    frame = flat_frame()
    frame.depth[:] = np.inf
    with pytest.raises(ValueError):
        project_box(frame, Pose((0, 0, 2)), (10, 10, 50, 50))


def test_box_clipped_to_image_and_empty_box_raises():
    frame = flat_frame()
    project_box(frame, Pose((0, 0, 2)), (-50, -50, 20, 20))
    with pytest.raises(ValueError):
        project_box(frame, Pose((0, 0, 2)), (300, 300, 400, 400))
