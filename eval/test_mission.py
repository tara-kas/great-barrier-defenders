"""Integration tests: the real Surveyor, FSM and output files working together.

Only the model is faked. PixelLLM finds coral in the rendered pixels, so boxes,
depth projection and registry merging all run for real.
"""

from __future__ import annotations

import io
import json
import re
import sys
from pathlib import Path

import numpy as np
import pytest
import requests
from PIL import Image
from scipy import ndimage

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:  # eval/ is not a package; make `agent`, `perception`, `eval` importable
    sys.path.insert(0, str(ROOT))

from agent.decision_log import DecisionLog  # noqa: E402
from agent.fsm import MissionFSM, PerceptionFailure  # noqa: E402
from eval.mock_robot import SAND_RGB, MockRobotInterface  # noqa: E402
from eval.synthetic_scene import generate_scene  # noqa: E402
from mission.runner import SurveyPerceiver, is_local_endpoint, run_mission  # noqa: E402
from perception.gemma_client import GemmaReply  # noqa: E402
from perception.registry import SemanticSeabedRegistry  # noqa: E402
from perception.survey import Surveyor  # noqa: E402
from perception.tests.fakes import cls_json, flat_frame  # noqa: E402


class PixelLLM:
    """Boxes come from real rendered pixels. Every third classification is DEAD."""

    def __init__(self) -> None:
        self.classifications = 0

    def ask(self, prompt, image_png, json_schema=None) -> GemmaReply:
        if '"objects"' in prompt:
            return GemmaReply(text=json.dumps({"objects": self._boxes(image_png)}), latency_ms=1.0)
        self.classifications += 1
        status = "DEAD" if self.classifications % 3 == 0 else "LIVE"
        return GemmaReply(text=cls_json(status=status, score=0.1 if status == "DEAD" else 0.9), latency_ms=1.0)

    @staticmethod
    def _boxes(image_png) -> list[dict]:
        pixels = np.asarray(Image.open(io.BytesIO(image_png)).convert("RGB")).astype(int)
        coral = (np.abs(pixels - np.array(SAND_RGB)).sum(2) > 30) & (pixels.sum(2) > 0)
        labelled, _ = ndimage.label(coral)
        height, width = coral.shape
        boxes = []
        for rows, cols in ndimage.find_objects(labelled):
            if (rows.stop - rows.start) * (cols.stop - cols.start) >= 30:
                box = [rows.start / height, cols.start / width, rows.stop / height, cols.stop / width]
                boxes.append({"label": "coral", "box_2d": [int(v * 1000) for v in box]})
        return boxes


class DownLLM:
    def ask(self, *args, **kwargs):
        raise requests.ConnectionError("endpoint unreachable")


class FlakyLLM(PixelLLM):
    """Fails the first N detection calls, then recovers."""

    def __init__(self, failures: int) -> None:
        super().__init__()
        self.failures = failures

    def ask(self, prompt, image_png, json_schema=None) -> GemmaReply:
        if '"objects"' in prompt and self.failures > 0:
            self.failures -= 1
            raise requests.ConnectionError("endpoint unreachable")
        return super().ask(prompt, image_png, json_schema)


class ClassifierDownLLM(PixelLLM):
    def ask(self, prompt, image_png, json_schema=None) -> GemmaReply:
        if '"objects"' not in prompt:
            raise requests.ConnectionError("endpoint unreachable")
        return super().ask(prompt, image_png, json_schema)


def mission(llm, tmp_path, robot=None, **overrides):
    robot = robot or MockRobotInterface(generate_scene(seed=0))
    kwargs = {
        "wait": robot.advance,
        "fragment_held": robot.fragment_held,
        "placement_verifier": robot.verify_placement,
        "out_dir": tmp_path,
    }
    return run_mission(robot, llm, **{**kwargs, **overrides}), robot


def saved_log(tmp_path) -> list:
    return DecisionLog.load(str(tmp_path / "decisions.jsonl")).entries


def test_real_perception_drives_a_full_mission(tmp_path):
    summary, robot = mission(PixelLLM(), tmp_path)
    assert summary.final_state == "MISSION_COMPLETE"
    assert summary.restored
    assert summary.unverified_placements == []
    assert len(robot.placements) == len(summary.restored)


def test_registry_positions_match_the_scene(tmp_path):
    scene = generate_scene(seed=0)
    mission(PixelLLM(), tmp_path, MockRobotInterface(scene))
    truth = np.array([e.position_world[:2] for e in scene.entries])
    saved = json.loads((tmp_path / "registry.json").read_text())["entries"]
    errors = [np.linalg.norm(truth - np.array(e["position_world"][:2]), axis=1).min() for e in saved]
    assert saved and max(errors) < 0.3


def test_gemma_reasoning_reaches_the_decision_log(tmp_path):
    mission(PixelLLM(), tmp_path)
    frames = [e for e in saved_log(tmp_path) if e.action == "survey_waypoint" and e.evidence["detections"]]
    observation = frames[0].evidence["perception"]["observations"][0]
    assert "confidence" in observation["classification"]
    assert "detect_latency_ms" in frames[0].evidence["perception"]
    assert frames[0].evidence["merged_by_perceiver"]


def test_gemma_down_aborts_instead_of_reporting_success(tmp_path):
    summary, _ = mission(DownLLM(), tmp_path)
    entries = saved_log(tmp_path)
    assert summary.final_state == "ABORTED"
    assert entries[-1].action == "abort"
    assert "perception unavailable" in entries[-1].outcome
    assert "unreachable" in entries[-1].evidence["error"]
    assert sum(e.action == "survey_waypoint_failed" for e in entries) == 2  # the third aborts


def test_classifier_down_also_aborts(tmp_path):
    summary, _ = mission(ClassifierDownLLM(), tmp_path)
    assert summary.final_state == "ABORTED"


def test_a_brief_outage_is_survived_and_recorded(tmp_path):
    summary, _ = mission(FlakyLLM(failures=2), tmp_path)
    entries = saved_log(tmp_path)
    assert summary.final_state == "MISSION_COMPLETE"
    survey = next(e for e in entries if e.action == "survey_complete")
    assert len(survey.evidence["failed_waypoints"]) == 2


def test_empty_seabed_is_not_a_failure():
    class NoCoral:
        def ask(self, *args, **kwargs):
            return GemmaReply(text='{"objects": []}', latency_ms=1.0)

    registry = SemanticSeabedRegistry()
    perceiver = SurveyPerceiver(Surveyor(NoCoral(), registry))
    assert perceiver(flat_frame(), pose()) == []


def test_unexpected_perception_error_becomes_a_failure():
    class Broken:
        registry = SemanticSeabedRegistry()

        def survey_frame(self, frame, pose):
            raise KeyError("bug")

    with pytest.raises(PerceptionFailure, match="KeyError"):
        SurveyPerceiver(Broken())(flat_frame(), pose())


def pose():
    from agent.robot_interface import Pose

    return Pose((0.0, 0.0, 2.0))


@pytest.mark.parametrize("missing", ["fragment_held", "placement_verifier"])
def test_refuses_to_run_without_safety_hooks(tmp_path, missing):
    with pytest.raises(ValueError, match=missing):
        mission(PixelLLM(), tmp_path, **{missing: None})


def test_unverified_run_is_possible_but_says_so(tmp_path):
    summary, _ = mission(PixelLLM(), tmp_path, placement_verifier=None, allow_unverified=True)
    placed = [e for e in saved_log(tmp_path) if e.action == "transplant_fragment"]
    assert placed and all(e.outcome == "placed, unverified" for e in placed)
    assert summary.unverified_placements == summary.restored


def test_failed_push_test_leaves_site_open_and_gives_up(tmp_path):
    robot = MockRobotInterface(generate_scene(seed=0))
    robot.unstable_next = 3  # the first site fails every attempt
    summary, _ = mission(PixelLLM(), tmp_path, robot)
    entries = saved_log(tmp_path)
    failed = [e for e in entries if e.action == "placement_unstable"]
    site = failed[0].evidence["recipient"]["cluster_id"]
    assert len(failed) == 3
    assert site not in summary.restored
    assert "push test" in summary.unrestorable[site]


@pytest.mark.parametrize("url,local", [
    ("http://localhost:8000/v1", True),
    ("http://127.0.0.1:8000/v1", True),
    ("https://team--reef-gemma-serve.modal.run/v1", False),
    ("https://localhost.example.com/v1", False),
])
def test_endpoint_locality(url, local):
    assert is_local_endpoint(url) is local


def test_remote_gemma_is_refused_unless_allowed(tmp_path):
    llm = PixelLLM()
    llm.base_url = "https://team--reef-gemma-serve.modal.run/v1"
    with pytest.raises(ValueError, match="not local"):
        mission(llm, tmp_path)
    assert mission(llm, tmp_path, allow_remote_perception=True)[0].final_state == "MISSION_COMPLETE"


def test_outputs_are_written_during_the_run_not_after(tmp_path):
    sizes = []
    mission(PixelLLM(), tmp_path, on_step=lambda _: sizes.append((tmp_path / "decisions.jsonl").stat().st_size))
    assert len(set(sizes)) > 10 and sizes == sorted(sizes)


def test_outputs_fit_the_dashboard_format(tmp_path):
    sys.path.insert(0, str(ROOT / "dashboard"))
    from server import read_decisions, read_registry

    seen = []

    def capture(_):
        seen.extend(json.loads((tmp_path / "registry.json").read_text())["detections"])

    mission(PixelLLM(), tmp_path, on_step=capture)
    entries, _ = read_registry(tmp_path / "registry.json")
    assert entries and read_decisions(tmp_path / "decisions.jsonl")
    assert (tmp_path / "frame.png").read_bytes().startswith(b"\x89PNG")
    assert seen
    for detection in seen:
        left, top, width, height = detection["box"]
        assert 0 <= left <= 1 and 0 <= top <= 1 and 0 < width <= 1 and 0 < height <= 1


def test_mission_log_works_with_the_debrief(tmp_path):
    from cloud.debrief import build_input

    mission(PixelLLM(), tmp_path)
    assert "survey_waypoint" in build_input(saved_log(tmp_path))


def test_agent_package_stays_free_of_network_code():
    """agent/CLAUDE.md: no network calls anywhere in agent/."""
    banned = re.compile(r"^\s*(?:import|from)\s+(requests|httpx|urllib|socket|aiohttp|google|perception\.(?:gemma_client|survey|classify|detect))\b", re.M)
    for path in (ROOT / "agent").rglob("*.py"):
        assert not banned.search(path.read_text(encoding="utf-8")), path


def test_fsm_without_perceiver_evidence_still_runs():
    robot = MockRobotInterface(generate_scene(seed=0))
    fsm = MissionFSM(robot, SemanticSeabedRegistry(), wait=robot.advance, perceiver=robot.perceiver())
    assert fsm.run(max_steps=2000).final_state == "MISSION_COMPLETE"
