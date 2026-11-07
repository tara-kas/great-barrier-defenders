"""The dataset's promises: labels agree with each other, and it fits the pipeline."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pytest
from PIL import Image

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:  # eval/ is not a package; make `agent`, `perception`, `eval` importable
    sys.path.insert(0, str(ROOT))

from agent.robot_interface import Pose, RGBDFrame  # noqa: E402
from eval.mock_robot import DOWN_CAMERA  # noqa: E402
from eval.moore_reef import (  # noqa: E402
    DATA_DIR, GENETS, MooreReefRobot, TextureSet, build_reef, match_genet, recovery_timeline, render_view,
)
from mission.runner import run_mission  # noqa: E402
from perception.classify import CORAL_TYPES, HEALTH_VALUES  # noqa: E402
from perception.gemma_client import GemmaReply  # noqa: E402
from perception.projection import project_box  # noqa: E402
from perception.registry import SemanticMapEntry, SemanticSeabedRegistry  # noqa: E402
from perception.survey import Surveyor  # noqa: E402
from perception.tests.fakes import cls_json  # noqa: E402


def load(name):
    return json.loads((DATA_DIR / name).read_text(encoding="utf-8"))


def load_jsonl(name):
    return [json.loads(line) for line in (DATA_DIR / name).read_text(encoding="utf-8").splitlines() if line]


@pytest.fixture(scope="module")
def reef():
    return build_reef()


@pytest.fixture(scope="module")
def frames():
    return load_jsonl("frames.jsonl")


def stored_frame(row) -> RGBDFrame:
    return RGBDFrame(
        rgb=np.asarray(Image.open(DATA_DIR / row["rgb"]).convert("RGB")),
        depth=np.asarray(Image.open(DATA_DIR / row["depth_mm"]), dtype=float) / 1000.0,
        intrinsics=tuple(row["intrinsics"]),
        camera_to_robot=np.array(row["camera_to_robot"]),
    )


def test_build_is_deterministic(reef):
    assert [c.label() for c in build_reef().clusters] == [c.label() for c in reef.clusters]


def test_stored_labels_match_the_definition(reef):
    assert load("labels.json") == json.loads(json.dumps([c.label() for c in reef.clusters]))


def test_labels_use_perception_vocabulary():
    for label in load("labels.json"):
        assert label["species_class"] in CORAL_TYPES
        assert label["health_status"] in HEALTH_VALUES


def test_health_scores_fit_perception_bands():
    bands = {"LIVE": (0.6, 1.0), "BLEACHED": (0.2, 0.7), "DEAD": (0.0, 0.3)}
    for label in load("labels.json"):
        low, high = bands[label["health_status"]]
        assert low <= label["health_score"] <= high


def test_every_expected_action_follows_from_the_data(reef):
    """Matching against the stock has to reach each label's expected action on its own."""
    for c in reef.clusters:
        if c.health_status == "DEAD":
            assert c.expected_action == "SKIP_DEAD" and c.genet_id is None
        elif c.health_status == "LIVE":
            assert c.expected_action == "LEAVE"
        else:
            matched, _ = match_genet(c.species_class, c.uv_signature)
            if c.expected_action == "TREAT":
                assert matched == c.genet_id
            else:
                assert matched is None, c.cluster_id


def test_scenario_covers_every_decision(reef):
    actions = {c.expected_action for c in reef.clusters}
    assert actions == {"TREAT", "SKIP_NO_MATCHING_GENET", "ABSTAIN_UV_MATCH_UNCERTAIN", "SKIP_DEAD", "LEAVE"}


def test_same_species_decoys_exist(reef):
    """Species matching alone must give wrong answers here, or genet logic goes untested."""
    treated = [c for c in reef.clusters if c.expected_action == "TREAT" and c.species_class == "pocillopora"]
    assert len({c.genet_id for c in treated}) == 2


def test_base_station_holds_only_stocked_genets():
    stocked = {r["genet_id"] for r in load("base_station.json")["racks"]}
    assert stocked == {k for k, g in GENETS.items() if g["stock"] > 0}
    assert stocked != set(GENETS)


def test_recovery_timeline_covers_treated_colonies(reef):
    timeline = recovery_timeline(reef)
    assert {r["cluster_id"] for r in timeline} == {c.cluster_id for c in reef.clusters if c.expected_action == "TREAT"}
    assert {r["outcome"] for r in timeline} == {"RECOVERED", "NOT_RECOVERED"}
    assert [o["day"] for o in timeline[0]["observations"]] == [0, 7, 56]
    assert load("recovery_timeline.json") == json.loads(json.dumps(timeline))


def test_registry_file_fits_the_frozen_contract():
    registry = SemanticSeabedRegistry()
    for row in load("registry.json"):
        registry.upsert(SemanticMapEntry(**row))
    assert len(registry.all()) == 20


def test_registry_loads_in_the_dashboard():
    sys.path.insert(0, str(ROOT / "dashboard"))
    from server import read_registry

    entries, _ = read_registry(DATA_DIR / "registry.json")
    assert len(entries) == 20


def test_all_frame_files_exist_and_line_up(frames):
    assert len(frames) == 25
    for row in frames:
        shapes = {np.asarray(Image.open(DATA_DIR / row[k])).shape[:2] for k in ("rgb", "uv", "depth_mm")}
        assert shapes == {(512, 512)}


def test_every_colony_is_seen(frames):
    assert {o["cluster_id"] for row in frames for o in row["objects"]} == {c["cluster_id"] for c in load("labels.json")}


def test_projecting_labelled_boxes_lands_on_the_colony(frames, reef):
    """Boxes, depth and pose together must put each colony where its label says."""
    for row in frames:
        frame = stored_frame(row)
        pose = Pose(tuple(row["pose"]["position"]), tuple(row["pose"]["orientation_quat"]))
        for obj in row["objects"]:
            x0, y0, x1, y1 = obj["box_xyxy"]
            if x0 <= 1 or y0 <= 1 or x1 >= 511 or y1 >= 511:
                continue  # a colony cut by the frame edge has an off-centre box
            shape = reef.cluster(obj["cluster_id"]).shape
            found = project_box(frame, pose, tuple(obj["box_xyxy"])).position_world
            assert np.hypot(found[0] - shape.center[0], found[1] - shape.center[1]) < 0.12


def test_colonies_are_whole_in_view(reef):
    """A colony in the middle of a frame must render as a full disc, with no bites."""
    textures = TextureSet()
    cluster = reef.clusters[0]
    x, y = cluster.shape.center
    view = render_view(reef, textures, Pose((x + 0.5, y + 0.3, 2.0)))
    rows, cols = np.nonzero(view.cluster_index == 0)
    width, height = cols.max() - cols.min() + 1, rows.max() - rows.min() + 1
    assert rows.size / (width * height) > 0.7  # a full disc fills about 78% of its box


@pytest.mark.parametrize("axis", [0, 1])
def test_seabed_has_no_straight_seams(axis):
    """No row or column boundary, including the wrap, may stand out from the rest."""
    tile = TextureSet().seabed()
    wrapped = np.concatenate([tile, np.take(tile, [0], axis=axis)], axis=axis)
    other = 1 - axis
    steps = np.abs(np.diff(wrapped, axis=axis)).mean(axis=(other, 2))
    assert steps.max() < 2.0 * np.median(steps)


def test_rgb_and_uv_show_the_same_colony(frames):
    """Same pixels, two modalities: colony pixels glow in UV, the seabed stays dark."""
    row = next(r for r in frames if r["objects"] and any(o["genet_id"] for o in r["objects"]))
    uv = np.asarray(Image.open(DATA_DIR / row["uv"]).convert("RGB"), dtype=float)
    obj = next(o for o in row["objects"] if o["genet_id"])
    x0, y0, x1, y1 = obj["box_xyxy"]
    assert uv[y0:y1, x0:x1].mean() > 3 * uv.mean(axis=(0, 1)).mean() / 2


def test_uv_colour_separates_decoy_genets(frames):
    crops = load_jsonl("crops.jsonl")

    def green_share(row):
        pixels = np.asarray(Image.open(DATA_DIR / row["uv"]).convert("RGB"), dtype=float).reshape(-1, 3)
        bright = pixels[pixels.sum(axis=1) > 200]
        return bright[:, 1].sum() / bright.sum()

    treated = {r["cluster_id"] for r in crops if r["expected_action"] == "TREAT"}
    pd1 = [green_share(r) for r in crops if r["genet_id"] == "PD-01" and r["cluster_id"] in treated]
    pd2 = [green_share(r) for r in crops if r["genet_id"] == "PD-02" and r["cluster_id"] in treated]
    assert min(pd1) > max(pd2)


class LabelledLLM:
    """Replays the dataset's labels as Gemma's answers, so the data itself is what's tested."""

    def __init__(self, robot):
        self.robot = robot

    def ask(self, prompt, image_png, json_schema=None):
        if '"objects"' in prompt:
            view = render_view(self.robot.reef, self.robot.textures, self.robot.get_pose())
            self.queue, boxes = [], []
            for index in np.unique(view.cluster_index):
                if index < 0:
                    continue
                rows, cols = np.nonzero(view.cluster_index == index)
                self.queue.append(self.robot.reef.clusters[index])
                height, width = view.cluster_index.shape
                boxes.append({"label": "coral", "box_2d": [int(rows.min() / height * 1000), int(cols.min() / width * 1000),
                                                           int(rows.max() / height * 1000), int(cols.max() / width * 1000)]})
            return GemmaReply(text=json.dumps({"objects": boxes}), latency_ms=1.0)
        cluster = self.queue.pop(0)
        return GemmaReply(text=cls_json(status=cluster.health_status, ctype=cluster.species_class,
                                        score=cluster.health_score), latency_ms=1.0)


def test_the_mission_runs_on_moore_reef(tmp_path):
    robot = MooreReefRobot()
    summary = run_mission(
        robot, LabelledLLM(robot), wait=robot.advance, fragment_held=robot.fragment_held,
        placement_verifier=robot.verify_placement, out_dir=tmp_path,
    )
    saved = json.loads((tmp_path / "registry.json").read_text())["entries"]
    assert summary.final_state == "MISSION_COMPLETE"
    assert len(saved) == 20
    assert {e["species_class"] for e in saved} == {c["species_class"] for c in load("labels.json")}


def test_surveyor_reads_stored_frames(frames):
    row = next(r for r in frames if len(r["objects"]) >= 3)

    class Replay:
        def __init__(self):
            self.objects = list(row["objects"])

        def ask(self, prompt, image_png, json_schema=None):
            if '"objects"' in prompt:
                boxes = [{"label": "coral", "box_2d": o["box_2d"]} for o in row["objects"]]
                return GemmaReply(text=json.dumps({"objects": boxes}), latency_ms=1.0)
            o = self.objects.pop(0)
            return GemmaReply(text=cls_json(status=o["health_status"], ctype=o["species_class"], score=o["health_score"]), latency_ms=1.0)

    registry = SemanticSeabedRegistry()
    pose = Pose(tuple(row["pose"]["position"]))
    result = Surveyor(Replay(), registry).survey_frame(stored_frame(row), pose)
    assert result.error is None
    assert len(registry.all()) == len(row["objects"])


def test_robot_uses_the_same_camera_contract():
    robot = MooreReefRobot()
    frame = robot.get_hull_rgbd()
    assert np.array_equal(frame.camera_to_robot, DOWN_CAMERA)
    assert np.asarray(frame.rgb).shape == (512, 512, 3)
    assert robot.get_uv_frame().shape == (512, 512, 3)
