import json

import numpy as np
import pytest
import requests

from agent.robot_interface import Pose
from perception.detect import DETECT_PROMPT
from perception.registry import GraftPose, SemanticSeabedRegistry
from perception.survey import Surveyor
from perception.tests.fakes import FakeLLM, cls_json, flat_frame

TWO_BOXES = json.dumps({"objects": [
    {"label": "coral", "box_2d": [400, 100, 600, 200]},  # left
    {"label": "coral", "box_2d": [400, 800, 600, 900]},  # right
]})
POSE = Pose((0, 0, 2))


def responder(cls_text, boxes=TWO_BOXES):
    def f(prompt, _img):
        if prompt == DETECT_PROMPT:
            return boxes
        if isinstance(cls_text, Exception):
            raise cls_text
        return cls_text
    return f


def test_new_clusters_created_with_world_positions():
    reg = SemanticSeabedRegistry()
    res = Surveyor(FakeLLM(responder(cls_json("DEAD", "pocillopora", 0.1, 0.9))), reg).survey_frame(flat_frame(), POSE)
    assert [o.action for o in res.observations] == ["new", "new"]
    entries = sorted(reg.all(), key=lambda e: e.position_world[0])
    assert [e.cluster_id for e in entries] == ["cluster_001", "cluster_002"]
    assert entries[0].position_world == pytest.approx((-1.4, 0, 0), abs=0.05)
    assert entries[1].position_world == pytest.approx((1.4, 0, 0), abs=0.05)
    assert all(e.health_status == "DEAD" and e.species_class == "pocillopora" for e in entries)
    ev = res.evidence()
    assert ev["observations"][0]["classification"]["confidence"] == 0.9
    json.dumps(ev)  # must be serialisable for the decision log


def test_reobservation_updates_instead_of_duplicating():
    reg = SemanticSeabedRegistry()
    s = Surveyor(FakeLLM(responder(cls_json("BLEACHED", score=0.5, conf=0.9))), reg)
    s.survey_frame(flat_frame(), POSE)
    res = s.survey_frame(flat_frame(), Pose((0.1, 0, 2)))  # small drift
    assert [o.action for o in res.observations] == ["updated", "updated"]
    assert len(reg.all()) == 2


@pytest.mark.parametrize("cls_text,reason", [
    (cls_json(conf=0.3), "confidence"),
    (cls_json(is_coral=False), "not coral"),
    ("garbage", "unparseable"),
    (requests.ConnectionError("down"), "unreachable"),
])
def test_abstains_and_writes_nothing(cls_text, reason):
    reg = SemanticSeabedRegistry()
    res = Surveyor(FakeLLM(responder(cls_text)), reg).survey_frame(flat_frame(), POSE)
    assert all(o.action == "abstained" and reason in o.reason for o in res.observations)
    assert reg.all() == []


def test_abstains_without_depth():
    frame = flat_frame()
    frame.depth[:] = np.nan
    reg = SemanticSeabedRegistry()
    res = Surveyor(FakeLLM(responder(cls_json())), reg).survey_frame(frame, POSE)
    assert all(o.action == "abstained" and "depth" in o.reason for o in res.observations)


def test_restored_entries_and_graft_pose_are_preserved():
    reg = SemanticSeabedRegistry()
    s = Surveyor(FakeLLM(responder(cls_json("DEAD", conf=0.8))), reg)
    s.survey_frame(flat_frame(), POSE)
    left, right = sorted(reg.all(), key=lambda e: e.position_world[0])
    left.health_status, left.sampled_or_restored = "TREATED", True
    gp = GraftPose((1, 0, 0), (0, 0, 0, 1), (0, 0, 1))
    right.optimal_graft_pose_world = gp

    res = s.survey_frame(flat_frame(), POSE)
    assert [o.action for o in res.observations] == ["kept", "updated"]
    assert reg.get(left.cluster_id).health_status == "TREATED"
    assert reg.get(right.cluster_id).optimal_graft_pose_world == gp


def test_less_confident_view_does_not_overwrite():
    reg = SemanticSeabedRegistry()
    answers = iter([cls_json("DEAD", conf=0.95)] * 2 + [cls_json("LIVE", conf=0.7)] * 2)
    s = Surveyor(FakeLLM(lambda p, i: TWO_BOXES if p == DETECT_PROMPT else next(answers)), reg)
    s.survey_frame(flat_frame(), POSE)
    res = s.survey_frame(flat_frame(), POSE)
    assert {o.action for o in res.observations} == {"kept"}
    assert {e.health_status for e in reg.all()} == {"DEAD"}


def test_detection_failure_reported_not_raised():
    reg = SemanticSeabedRegistry()
    res = Surveyor(FakeLLM(responder(cls_json(), boxes="nope")), reg).survey_frame(flat_frame(), POSE)
    assert res.error and res.observations == []


def box_reply(box):
    return json.dumps({"objects": [{"label": "coral", "box_2d": box}]})


def survey(reg, surveyor_boxes):
    llm_boxes = iter(surveyor_boxes)

    def f(prompt, _img):
        return box_reply(next(llm_boxes)) if prompt == DETECT_PROMPT else cls_json()

    surveyor = Surveyor(FakeLLM(f), reg)
    return [surveyor.survey_frame(flat_frame(), POSE) for _ in surveyor_boxes]


WHOLE = [300, 800, 700, 980]
CLIPPED = [300, 800, 700, 1000]  # the same colony, running off the right edge


def test_view_cut_off_by_the_frame_edge_cannot_replace_a_complete_one():
    reg = SemanticSeabedRegistry()
    results = survey(reg, [WHOLE, CLIPPED])
    assert results[1].observations[0].action == "kept"
    assert "frame edge" in results[1].observations[0].reason
    assert len(reg.all()) == 1
    alone = SemanticSeabedRegistry()
    survey(alone, [WHOLE])
    assert reg.all()[0].bounding_box_extent == alone.all()[0].bounding_box_extent


def test_complete_view_replaces_a_clipped_one():
    reg = SemanticSeabedRegistry()
    results = survey(reg, [CLIPPED, WHOLE])
    assert results[1].observations[0].action == "updated"
    assert len(reg.all()) == 1
