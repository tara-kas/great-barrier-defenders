"""Connects perception, the FSM and the dashboard for one mission.

`run_mission` is the single entry point: the mock harness and the Isaac Sim
adapter both call it, so both exercise the same wiring. The sim side supplies a
`RobotInterface`, plus `fragment_held` and `placement_verifier`, which are what
make the dislodgement and push-test behaviour real.

This lives outside agent/ on purpose: agent/ must stay free of network code,
and this module is where the model client meets the FSM.
"""

from __future__ import annotations

import json
import logging
import os
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Callable, Optional
from urllib.parse import urlsplit

import numpy as np

from agent.config import FSMConfig
from agent.decision_log import DecisionLog
from agent.fsm import MissionFSM, MissionSummary, PerceptionFailure
from agent.robot_interface import Pose, RGBDFrame, RobotInterface
from perception.gemma_client import VisionLLM, encode_png
from perception.registry import SemanticMapEntry, SemanticSeabedRegistry
from perception.survey import Surveyor

log = logging.getLogger(__name__)

LOCAL_HOSTS = {"localhost", "127.0.0.1", "::1"}
CLASSIFIER_UNREACHABLE = "classifier unreachable"


class SurveyPerceiver:
    """Adapts `Surveyor` to the FSM's perceiver hook.

    The Surveyor writes the registry itself, so this returns the entries it
    touched. A frame that could not be processed raises PerceptionFailure, which
    keeps "the model was down" distinct from "there is no coral here".
    """

    def __init__(self, surveyor: Surveyor) -> None:
        self.surveyor = surveyor
        self.last_evidence: Optional[dict[str, Any]] = None
        self.last_frame: Optional[RGBDFrame] = None
        self.last_boxes: list[dict[str, Any]] = []

    def __call__(self, frame: RGBDFrame, pose: Pose) -> list[SemanticMapEntry]:
        self.last_frame = frame
        self.last_boxes = []
        try:
            result = self.surveyor.survey_frame(frame, pose)
        except Exception as err:  # A perception bug must not take the vehicle's control loop down.
            self.last_evidence = {"error": f"{type(err).__name__}: {err}"}
            raise PerceptionFailure(self.last_evidence["error"]) from err

        self.last_evidence = result.evidence()
        if result.error:
            raise PerceptionFailure(result.error)
        observations = result.observations
        if observations and all(o.reason.startswith(CLASSIFIER_UNREACHABLE) for o in observations):
            raise PerceptionFailure(f"{CLASSIFIER_UNREACHABLE} for all {len(observations)} detections")

        height, width = np.asarray(frame.rgb).shape[:2]
        self.last_boxes = [_dashboard_box(o, width, height) for o in observations if o.cluster_id]
        cluster_ids = dict.fromkeys(o.cluster_id for o in observations if o.cluster_id)
        entries = (self.surveyor.registry.get(cid) for cid in cluster_ids)
        return [e for e in entries if e is not None]


def _dashboard_box(observation: Any, width: int, height: int) -> dict[str, Any]:
    x0, y0, x1, y1 = observation.detection.box_xyxy
    box = [x0 / width, y0 / height, (x1 - x0) / width, (y1 - y0) / height]
    return {"cluster_id": observation.cluster_id, "box": box}


def _write_atomic(path: Path, data: bytes) -> None:
    """The dashboard polls these files, so it must never read a half-written one."""
    temp = path.with_name(path.name + ".tmp")
    temp.write_bytes(data)
    os.replace(temp, path)


class LiveOutputs:
    """Writes the files the dashboard and debrief read, after every FSM step."""

    def __init__(self, out_dir: Path) -> None:
        self.out_dir = Path(out_dir)
        self.out_dir.mkdir(parents=True, exist_ok=True)
        self.registry_path = self.out_dir / "registry.json"
        self.log_path = self.out_dir / "decisions.jsonl"
        self.frame_path = self.out_dir / "frame.png"
        self.summary_path = self.out_dir / "summary.json"

    def write(self, fsm: MissionFSM, perceiver: SurveyPerceiver) -> None:
        state = {"entries": fsm.registry.dump(), "detections": perceiver.last_boxes}
        try:
            _write_atomic(self.registry_path, json.dumps(state).encode("utf-8"))
            _write_atomic(self.log_path, fsm.log.to_jsonl().encode("utf-8"))
            if perceiver.last_frame is not None:
                _write_atomic(self.frame_path, encode_png(perceiver.last_frame.rgb))
        except OSError as err:  # A full disk must not stop the mission.
            log.warning("could not write live outputs: %s", err)

    def write_summary(self, summary: MissionSummary) -> None:
        _write_atomic(self.summary_path, json.dumps(asdict(summary), indent=2).encode("utf-8"))


def is_local_endpoint(url: str) -> bool:
    return urlsplit(url).hostname in LOCAL_HOSTS


def _check_safeguards(
    llm: VisionLLM,
    fragment_held: Optional[Callable[[], bool]],
    placement_verifier: Optional[Callable[[Pose], dict]],
    allow_unverified: bool,
    allow_remote_perception: bool,
) -> None:
    missing = [
        name
        for name, hook in (("fragment_held", fragment_held), ("placement_verifier", placement_verifier))
        if hook is None
    ]
    if missing and not allow_unverified:
        raise ValueError(
            f"run_mission needs {' and '.join(missing)}: without them a lost fragment goes "
            "unnoticed and placements are never checked. Pass allow_unverified=True to run anyway."
        )
    base_url = getattr(llm, "base_url", None)
    if base_url and not is_local_endpoint(base_url) and not allow_remote_perception:
        raise ValueError(
            f"perception endpoint {base_url} is not local, so the dive would depend on a network "
            "link. Serve Gemma on this machine, or pass allow_remote_perception=True for development."
        )


def run_mission(
    robot: RobotInterface,
    llm: VisionLLM,
    *,
    wait: Callable[[float], None],
    fragment_held: Optional[Callable[[], bool]],
    placement_verifier: Optional[Callable[[Pose], dict]],
    out_dir: Path,
    config: FSMConfig = FSMConfig(),
    registry: Optional[SemanticSeabedRegistry] = None,
    on_step: Optional[Callable[[MissionFSM], None]] = None,
    max_steps: int = 2000,
    allow_unverified: bool = False,
    allow_remote_perception: bool = False,
) -> MissionSummary:
    """Survey with real perception, then run the mission. `on_step` is the director hook."""
    _check_safeguards(llm, fragment_held, placement_verifier, allow_unverified, allow_remote_perception)

    registry = registry if registry is not None else SemanticSeabedRegistry()
    perceiver = SurveyPerceiver(Surveyor(llm, registry))
    outputs = LiveOutputs(out_dir)
    fsm = MissionFSM(
        robot,
        registry,
        config=config,
        log=DecisionLog(),
        wait=wait,
        perceiver=perceiver,
        fragment_held=fragment_held,
        placement_verifier=placement_verifier,
    )

    def after_step(current: MissionFSM) -> None:
        outputs.write(current, perceiver)
        if on_step is not None:
            on_step(current)

    outputs.write(fsm, perceiver)
    summary = fsm.run(max_steps=max_steps, on_step=after_step)
    outputs.write(fsm, perceiver)  # Picks up the abort entry run() adds after the last step.
    outputs.write_summary(summary)
    return summary
