"""Mechanical connection regressions for narrow and broad scanned cuttings."""
import math

from reefsim.gripper_linkage import (
    CARRIAGE_SIZE, PALM_CENTER, PALM_SIZE, WRIST_CENTER, jaw_linkage,
)


def inside(point, center, size):
    return all(abs(p-c) <= s/2+1e-10 for p, c, s in zip(point, center, size))


def test_wide_natural_cutting_jaws_stay_connected_through_their_full_travel():
    # 46.85 mm is the branch selected by the recorded mission. Previously its
    # open finger lay outside the 60 mm half-width palm with no connecting rail.
    for radius in (.003, .012, .04684939426236898, .065):
        for opening in (0., .1, .5, .9, 1.):
            for jaw in jaw_linkage(radius, opening):
                assert inside(jaw["rail_start"], PALM_CENTER, PALM_SIZE)
                assert inside(jaw["rail_end"], jaw["carriage"], CARRIAGE_SIZE)
                # The proximal capsule centreline must enter the carriage.
                proximal = (-.027-.065/2, jaw["finger"][1], 0.)
                assert inside(proximal, jaw["carriage"], CARRIAGE_SIZE)


def test_wrist_knuckle_covers_both_forearm_endpoint_and_palm():
    # Rotation about any heading preserves the shared wrist attachment and
    # the 8.5 mm knuckle/palm overlap; test the coordinate systems explicitly.
    for body_yaw in (-math.pi, -.7, 0., 1.2):
        for wrist_yaw in (-math.pi, -1.3, 0., .8, math.pi):
            def rotate(point, angle):
                c, s = math.cos(angle), math.sin(angle)
                return (point[0]*c-point[1]*s, point[0]*s+point[1]*c, point[2])
            body_wrist = rotate(WRIST_CENTER, wrist_yaw)
            forearm_world = rotate(body_wrist, body_yaw)
            knuckle_world = rotate(WRIST_CENTER, body_yaw+wrist_yaw)
            assert math.dist(forearm_world, knuckle_world) < 1e-12
    nearest_palm_x = PALM_CENTER[0]-PALM_SIZE[0]/2
    assert abs(nearest_palm_x-WRIST_CENTER[0]) < .031
