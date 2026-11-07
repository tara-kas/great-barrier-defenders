"""Integration tests: the real Surveyor, FSM and output files working together.

Only the model is faked (ScenarioLLM), so depth projection, UV genet reading,
planning and placement all run for real.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

import numpy as np
import pytest
import requests

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:  # eval/ is not a package; make `agent`, `perception`, `eval` importable
    sys.path.insert(0, str(ROOT))

from agent.decision_log import DecisionLog  # noqa: E402
from agent.fsm import MissionFSM, PerceptionFailure  # noqa: E402
from eval.mock_robot import MockRobotInterface  # noqa: E402
from eval.moore_reef import MooreReefRobot, genet_library, moore_station, recovery_timeline  # noqa: E402
from eval.scenario_llm import ScenarioLLM  # noqa: E402
from eval.synthetic_scene import generate_scene  # noqa: E402
from mission.runner import SurveyPerceiver, is_local_endpoint, run_mission  # noqa: E402
from perception.gemma_client import GemmaReply  # noqa: E402
from perception.registry import SemanticSeabedRegistry  # noqa: E402
from perception.survey import Surveyor  # noqa: E402
from perception.tests.fakes import flat_frame  # noqa: E402


class DownLLM:
    def ask(self, *args, **kwargs):
        raise requests.ConnectionError("endpoint unreachable")


class FlakyLLM(ScenarioLLM):
    """Fails the first N detection calls, then recovers."""

    def __init__(self, robot, failures: int) -> None:
        super().__init__(robot)
        self.failures = failures

    def ask(self, prompt, image_png, json_schema=None) -> GemmaReply:
        if '"objects"' in prompt and self.failures > 0:
            self.failures -= 1
            raise requests.ConnectionError("endpoint unreachable")
        return super().ask(prompt, image_png, json_schema)


class ClassifierDownLLM(ScenarioLLM):
    def ask(self, prompt, image_png, json_schema=None) -> GemmaReply:
        if '"objects"' not in prompt:
            raise requests.ConnectionError("endpoint unreachable")
        return super().ask(prompt, image_png, json_schema)


def mission(make_llm, tmp_path, **overrides):
    """Runs Moore Reef. make_llm builds the model stand-in from the robot."""
    robot = MooreReefRobot()
    kwargs = {
        "base_station": moore_station(),
        "genet_library": genet_library(),
        "wait": robot.advance,
        "fragment_held": robot.fragment_held,
        "placement_verifier": robot.verify_placement,
        "out_dir": tmp_path,
    }
    return run_mission(robot, make_llm(robot), **{**kwargs, **overrides}), robot


def saved_log(tmp_path) -> list:
    return DecisionLog.load(str(tmp_path / "decisions.jsonl")).entries


def by_true_cluster(saved: list[dict], robot) -> dict:
    """Saved registry rows keyed by the scenario colony each one sits on."""
    out = {}
    for row in saved:
        x, y = row["position_world"][:2]
        c = min(robot.reef.clusters, key=lambda c: np.hypot(c.shape.center[0] - x, c.shape.center[1] - y))
        assert c.cluster_id not in out, "two registry rows on one colony"
        out[c.cluster_id] = row
    return out


def test_every_colony_gets_its_expected_action(tmp_path):
    """The whole pipeline: survey, UV genet reading, planning, placement, on all 20 colonies."""
    summary, robot = mission(ScenarioLLM, tmp_path)
    saved = json.loads((tmp_path / "registry.json").read_text())["entries"]
    rows = by_true_cluster(saved, robot)
    assert summary.final_state == "MISSION_COMPLETE"
    assert len(rows) == 20
    expected_status = {
        "TREAT": "TREATED",
        "SKIP_NO_MATCHING_GENET": "BLEACHED",
        "ABSTAIN_UV_MATCH_UNCERTAIN": "BLEACHED",
        "SKIP_DEAD": "DEAD",
        "LEAVE": "LIVE",
    }
    for c in robot.reef.clusters:
        assert rows[c.cluster_id]["health_status"] == expected_status[c.expected_action], c.cluster_id
    assert len(robot.placements) == 8
    assert summary.unverified_placements == []


def test_skip_reasons_match_the_scenario(tmp_path):
    summary, robot = mission(ScenarioLLM, tmp_path)
    rows = by_true_cluster(json.loads((tmp_path / "registry.json").read_text())["entries"], robot)
    for c in robot.reef.clusters:
        reason = summary.skipped.get(rows[c.cluster_id]["cluster_id"], "")
        if c.expected_action == "SKIP_NO_MATCHING_GENET":
            assert "not in stock" in reason
        elif c.expected_action == "ABSTAIN_UV_MATCH_UNCERTAIN":
            assert reason == "no confident UV genet match"


def test_each_fragment_goes_to_its_own_genet(tmp_path):
    """Genets are read from UV pixels here, and every pairing must match the true genet."""
    _, robot = mission(ScenarioLLM, tmp_path)
    rows = by_true_cluster(json.loads((tmp_path / "registry.json").read_text())["entries"], robot)
    for c in robot.reef.clusters:
        if c.expected_action == "TREAT":
            assert rows[c.cluster_id]["genet_id"] == c.genet_id


def test_stock_is_used_exactly_once_per_treated_colony(tmp_path):
    station = moore_station()
    before = sum(station.stock().values())
    mission(ScenarioLLM, tmp_path, base_station=station)
    assert before - sum(station.stock().values()) == 8


def test_return_visits_reach_the_scenario_outcomes(tmp_path):
    summary, robot = mission(ScenarioLLM, tmp_path, revisit_observer=None)
    robot2 = MooreReefRobot()
    summary, robot = mission(ScenarioLLM, tmp_path, revisit_observer=robot2.observe_recovery)
    rows = by_true_cluster(json.loads((tmp_path / "registry.json").read_text())["entries"], robot)
    for record in recovery_timeline(robot.reef):
        assert rows[record["cluster_id"]]["health_status"] == record["outcome"]
    assert sum(e.action == "revisit_complete" for e in saved_log(tmp_path)) == 2


def test_registry_positions_match_the_scene(tmp_path):
    _, robot = mission(ScenarioLLM, tmp_path)
    saved = json.loads((tmp_path / "registry.json").read_text())["entries"]
    truth = np.array([c.shape.center for c in robot.reef.clusters])
    errors = [np.linalg.norm(truth - np.array(e["position_world"][:2]), axis=1).min() for e in saved]
    assert max(errors) < 0.1


def test_gemma_reasoning_reaches_the_decision_log(tmp_path):
    mission(ScenarioLLM, tmp_path)
    frames = [e for e in saved_log(tmp_path) if e.action == "survey_waypoint" and e.evidence["detections"]]
    observation = frames[0].evidence["perception"]["observations"][0]
    assert "confidence" in observation["classification"]
    assert "detect_latency_ms" in frames[0].evidence["perception"]
    assert frames[0].evidence["merged_by_perceiver"]


def test_uv_reasoning_reaches_the_decision_log(tmp_path):
    mission(ScenarioLLM, tmp_path)
    readings = [
        o["genet"]
        for e in saved_log(tmp_path) if e.action == "survey_waypoint"
        for o in e.evidence["perception"]["observations"] if "genet" in o
    ]
    assert readings and all("uv_signature" in r for r in readings)
    assert {"genet_id", "distance", "nearest"} <= set(readings[0])


def test_gemma_down_aborts_instead_of_reporting_success(tmp_path):
    summary, _ = mission(lambda r: DownLLM(), tmp_path)
    entries = saved_log(tmp_path)
    assert summary.final_state == "ABORTED"
    assert entries[-1].action == "abort"
    assert "perception unavailable" in entries[-1].outcome
    assert "unreachable" in entries[-1].evidence["error"]
    assert sum(e.action == "survey_waypoint_failed" for e in entries) == 2  # the third aborts


def test_classifier_down_also_aborts(tmp_path):
    summary, _ = mission(ClassifierDownLLM, tmp_path)
    assert summary.final_state == "ABORTED"


def test_a_brief_outage_is_survived_and_recorded(tmp_path):
    summary, _ = mission(lambda r: FlakyLLM(r, failures=2), tmp_path)
    entries = saved_log(tmp_path)
    assert summary.final_state == "MISSION_COMPLETE"
    survey = next(e for e in entries if e.action == "survey_complete")
    assert len(survey.evidence["failed_waypoints"]) == 2


def test_empty_seabed_is_not_a_failure():
    class NoCoral:
        def ask(self, *args, **kwargs):
            return GemmaReply(text='{"objects": []}', latency_ms=1.0)

    registry = SemanticSeabedRegistry()
    perceiver = SurveyPerceiver(Surveyor(NoCoral(), registry), lambda: flat_frame().rgb, genet_library())
    assert perceiver(flat_frame(), pose()) == []


def test_unexpected_perception_error_becomes_a_failure():
    class Broken:
        registry = SemanticSeabedRegistry()

        def survey_frame(self, frame, pose):
            raise KeyError("bug")

    with pytest.raises(PerceptionFailure, match="KeyError"):
        SurveyPerceiver(Broken(), lambda: None, [])(flat_frame(), pose())


def pose():
    from agent.robot_interface import Pose

    return Pose((0.0, 0.0, 2.0))


@pytest.mark.parametrize("missing", ["fragment_held", "placement_verifier"])
def test_refuses_to_run_without_safety_hooks(tmp_path, missing):
    with pytest.raises(ValueError, match=missing):
        mission(ScenarioLLM, tmp_path, **{missing: None})


def test_unverified_run_is_possible_but_says_so(tmp_path):
    summary, _ = mission(ScenarioLLM, tmp_path, placement_verifier=None, allow_unverified=True)
    placed = [e for e in saved_log(tmp_path) if e.action == "transplant_fragment"]
    assert placed and all(e.outcome == "placed, unverified" for e in placed)
    assert summary.unverified_placements == summary.treated


def test_failed_push_test_leaves_site_open_and_gives_up(tmp_path):
    fails = {"left": 3}

    def verifier(pose):
        fails["left"] -= 1
        return {"stable": fails["left"] < 0, "contact": True}

    summary, _ = mission(ScenarioLLM, tmp_path, placement_verifier=verifier)
    failed = [e for e in saved_log(tmp_path) if e.action == "placement_unstable"]
    site = failed[0].evidence["recipient"]["cluster_id"]
    assert len(failed) == 3
    assert site not in summary.treated
    assert "push test" in summary.skipped[site]


@pytest.mark.parametrize("url,local", [
    ("http://localhost:8000/v1", True),
    ("http://127.0.0.1:8000/v1", True),
    ("https://team--reef-gemma-serve.modal.run/v1", False),
    ("https://localhost.example.com/v1", False),
])
def test_endpoint_locality(url, local):
    assert is_local_endpoint(url) is local


def remote(robot):
    llm = ScenarioLLM(robot)
    llm.base_url = "https://team--reef-gemma-serve.modal.run/v1"
    return llm


def test_remote_gemma_is_refused_unless_allowed(tmp_path):
    with pytest.raises(ValueError, match="not local"):
        mission(remote, tmp_path)
    assert mission(remote, tmp_path, allow_remote_perception=True)[0].final_state == "MISSION_COMPLETE"


def test_outputs_are_written_during_the_run_not_after(tmp_path):
    sizes = []
    mission(ScenarioLLM, tmp_path, on_step=lambda _: sizes.append((tmp_path / "decisions.jsonl").stat().st_size))
    assert len(set(sizes)) > 10 and sizes == sorted(sizes)


def test_outputs_fit_the_dashboard_format(tmp_path):
    sys.path.insert(0, str(ROOT / "dashboard"))
    from server import read_decisions, read_registry

    seen = []

    def capture(_):
        seen.extend(json.loads((tmp_path / "registry.json").read_text())["detections"])

    mission(ScenarioLLM, tmp_path, on_step=capture)
    entries, _ = read_registry(tmp_path / "registry.json")
    assert entries and read_decisions(tmp_path / "decisions.jsonl")
    assert (tmp_path / "frame.png").read_bytes().startswith(b"\x89PNG")
    assert seen
    for detection in seen:
        left, top, width, height = detection["box"]
        assert 0 <= left <= 1 and 0 <= top <= 1 and 0 < width <= 1 and 0 < height <= 1


def test_mission_log_works_with_the_debrief(tmp_path):
    from cloud.debrief import build_input

    mission(ScenarioLLM, tmp_path)
    assert "survey_waypoint" in build_input(saved_log(tmp_path))


def test_agent_package_stays_free_of_network_code():
    """agent/CLAUDE.md: no network calls anywhere in agent/."""
    banned = re.compile(r"^\s*(?:import|from)\s+(requests|httpx|urllib|socket|aiohttp|google|perception\.(?:gemma_client|survey|classify|detect))\b", re.M)
    for path in (ROOT / "agent").rglob("*.py"):
        assert not banned.search(path.read_text(encoding="utf-8")), path


def test_fsm_without_perceiver_evidence_still_runs():
    scene = generate_scene(seed=0)
    robot = MockRobotInterface(scene)
    fsm = MissionFSM(
        robot, SemanticSeabedRegistry(), base_station=scene.base_station(), wait=robot.advance, perceiver=robot.perceiver()
    )
    assert fsm.run(max_steps=2000).final_state == "MISSION_COMPLETE"
