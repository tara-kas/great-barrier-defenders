"""Fault injection at the legacy mission's configuration and actuator boundary."""

from types import SimpleNamespace
from unittest.mock import Mock

import numpy as np
import pytest

from agent.base_station import BaseStation
from agent.config import FSMConfig, GraftConfig, NavConfig, PairingWeights
from agent.fsm import MissionFSM
from agent.robot_interface import Pose
from perception.registry import SemanticSeabedRegistry


ZERO = (0.0, 0.0, 0.0)


def mission(*, config=FSMConfig()):
    robot = SimpleNamespace(get_pose=Mock(return_value=Pose(ZERO)), set_cmd_vel=Mock())
    fsm = MissionFSM(robot, SemanticSeabedRegistry(), base_station=BaseStation(ZERO, []),
                     config=config, wait=Mock(), fragment_held=Mock(return_value=True))
    return fsm, robot


@pytest.mark.parametrize("source", ["wait", "pose", "monitor", "actuator"])
def test_navigation_stops_when_a_callback_fails_after_motion(source):
    fsm, robot = mission()
    failure = RuntimeError("injected navigation failure")
    if source == "wait":
        fsm.wait.side_effect = failure
    elif source == "pose":
        robot.get_pose.side_effect = [Pose(ZERO), Pose(ZERO), failure]
    elif source == "monitor":
        fsm.fragment_held.side_effect = [True, failure]
    else:
        robot.set_cmd_vel.side_effect = [failure, None]
    with pytest.raises(RuntimeError, match="injected navigation failure"):
        fsm._navigate(Pose((1.0, 0.0, 0.0)), carrying=True)
    commands = robot.set_cmd_vel.call_args_list
    assert commands[0].args[0] != ZERO
    assert commands[-1].args == (ZERO, ZERO)


@pytest.mark.parametrize("bad_pose", [
    Pose((float("nan"), 0.0, 0.0)),
    Pose((0.0, float("inf"), 0.0)),
    Pose(ZERO, (0.0, 0.0, float("nan"), 1.0)),
    Pose((1.0, 2.0)),
])
@pytest.mark.parametrize("source", ["target", "sensor"])
def test_invalid_pose_never_reaches_actuator(bad_pose, source):
    fsm, robot = mission()
    target = Pose((1.0, 0.0, 0.0))
    if source == "target":
        target = bad_pose
    else:
        robot.get_pose.return_value = bad_pose
    with pytest.raises(ValueError, match="finite position"):
        fsm._navigate(target, carrying=False)
    robot.set_cmd_vel.assert_called_once_with(ZERO, ZERO)


def test_nonfinite_pose_after_motion_stops_without_forwarding_nan():
    fsm, robot = mission()
    robot.get_pose.side_effect = [Pose(ZERO), Pose(ZERO), Pose((float("nan"), 0.0, 0.0))]
    with pytest.raises(ValueError):
        fsm._navigate(Pose((1.0, 0.0, 0.0)), carrying=False)
    assert len(robot.set_cmd_vel.call_args_list) == 2
    for call in robot.set_cmd_vel.call_args_list:
        assert np.isfinite(call.args).all()
    robot.set_cmd_vel.assert_called_with(ZERO, ZERO)


def test_finite_inputs_that_overflow_velocity_stop_before_motion():
    fsm, robot = mission(config=FSMConfig(nav=NavConfig(gain=1e308)))
    with pytest.raises(ValueError, match="velocity"):
        fsm._navigate(Pose((10.0, 0.0, 0.0)), carrying=False)
    robot.set_cmd_vel.assert_called_once_with(ZERO, ZERO)


@pytest.mark.parametrize("terminal", ["arrived", "timeout", "dislodged"])
def test_normal_navigation_exits_also_stop(terminal):
    fsm, robot = mission(config=FSMConfig(nav=NavConfig(timeout_s=0.1)))
    if terminal == "arrived":
        robot.get_pose.return_value = Pose((1.0, 0.0, 0.0))
    elif terminal == "dislodged":
        fsm.fragment_held.return_value = False
    status, _ = fsm._navigate(Pose((1.0, 0.0, 0.0)), carrying=True)
    assert status == terminal
    robot.set_cmd_vel.assert_called_with(ZERO, ZERO)


@pytest.mark.parametrize("patch", [
    {"nav": {"dt": 0}},
    {"nav": {"dt": -0.1}},
    {"nav": {"timeout_s": 0}},
    {"nav": {"max_speed": float("inf")}},
    {"nav": {"gain": float("nan")}},
    {"nav": {"carry_speed_scale": -1}},
    {"weights": {"w1": float("nan")}},
    {"graft": {"reach_radius": float("inf")}},
    {"graft": {"k_neighbors": 0}},
    {"graft": {"max_candidates": 0}},
    {"harvest_ik_attempts": 0},
    {"max_attempts_per_recipient": -1},
    {"max_perception_failures": 0},
    {"harvest_ik_attempts": 1.5},
    {"reobserve_attempts": -1},
    {"survey_swath": 0},
    {"survey_bounds": [0, 1, 0, float("nan")]},
    {"min_donor_health": float("nan")},
    {"nav": None},
])
def test_invalid_config_rejected_before_mission(patch):
    with pytest.raises(ValueError):
        FSMConfig.from_dict(patch)


@pytest.mark.parametrize("construct", [
    lambda: NavConfig(dt=0),
    lambda: GraftConfig(max_candidates=0),
    lambda: PairingWeights(w1=float("nan")),
    lambda: FSMConfig(harvest_ik_attempts=0),
])
def test_direct_configuration_construction_is_also_validated(construct):
    with pytest.raises(ValueError):
        construct()


def test_existing_empty_survey_and_optional_revisits_roundtrip():
    config = FSMConfig(survey_bounds=(-2.9, -2.9, -3.4, -3.4),
                       revisit_days=(), reobserve_attempts=0,
                       weights=PairingWeights(w3=0))
    assert FSMConfig.from_dict(config.to_dict()) == config
