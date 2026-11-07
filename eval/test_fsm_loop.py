"""End-to-end regression suite for agent/fsm.py on the mock robot + synthetic scene.

Any patch to agent/ (including Argon-proposed config or code changes) must keep
this passing before merge (CLAUDE.md section 8).

    python -m pytest eval/test_fsm_loop.py
    python eval/test_fsm_loop.py --out agent/samples   # regenerate the sample log
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:  # eval/ is not a package; make `agent`, `perception`, `eval` importable
    sys.path.insert(0, str(ROOT))

import json  # noqa: E402

import numpy as np  # noqa: E402
import pytest  # noqa: E402

from agent.config import FSMConfig  # noqa: E402
from agent.decision_log import DecisionLog  # noqa: E402
from agent.fsm import MissionFSM, MissionState  # noqa: E402
from eval.mock_robot import MockRobotInterface  # noqa: E402
from eval.synthetic_scene import SyntheticScene, generate_scene  # noqa: E402
from perception.registry import SemanticSeabedRegistry  # noqa: E402


def make_mission(scene: SyntheticScene, *, survey: bool = False, config: FSMConfig = FSMConfig(), station=None):
    robot = MockRobotInterface(scene)
    registry = SemanticSeabedRegistry() if survey else scene.registry()
    fsm = MissionFSM(
        robot,
        registry,
        base_station=station or scene.base_station(),
        config=config,
        wait=robot.advance,
        perceiver=robot.perceiver() if survey else None,
        fragment_held=robot.fragment_held,
    )
    return fsm, robot, registry


def assert_log_well_formed(log: DecisionLog) -> None:
    assert log.entries, "empty decision log"
    for i, e in enumerate(log.entries):
        assert e.action, f"entry {i} has no action"
        assert e.evidence, f"entry {i} ({e.action}) has no evidence"
        for key in ("next_state", "rov_pose", "sim_time_s"):
            assert key in e.evidence, f"entry {i} ({e.action}) missing {key}"
        json.dumps(e.evidence)  # JSON-safe
    # Transitions chain: each entry's next_state is the state the next entry was logged in.
    for prev, nxt in zip(log.entries, log.entries[1:]):
        assert prev.evidence["next_state"] == nxt.state, (prev.action, nxt.action)


def actions(log: DecisionLog) -> list[str]:
    return [e.action for e in log.entries]


def free_spot(scene: SyntheticScene, clearance: float = 0.9) -> tuple[float, float]:
    xmin, xmax, ymin, ymax = scene.bounds
    for x in np.arange(xmin + 0.6, xmax - 0.6, 0.2):
        for y in np.arange(ymin + 0.6, ymax - 0.6, 0.2):
            if all(np.hypot(x - s.center[0], y - s.center[1]) >= clearance for s in scene.shapes.values()):
                return (float(x), float(y))
    raise RuntimeError("no free spot")


@pytest.fixture
def scene() -> SyntheticScene:
    return generate_scene(seed=0)


# ---------------------------------------------------------------- baseline


def test_scene_matches_spec(scene):
    assert 15 <= len(scene.entries) <= 20
    assert len({e.species_class for e in scene.entries}) in (2, 3)
    assert {"LIVE", "DEAD", "BLEACHED"} <= {e.health_status for e in scene.entries}
    for e in scene.entries:
        assert 0 <= e.position_world[0] <= 10 and 0 <= e.position_world[1] <= 10


def test_every_bleached_colony_treated(scene, tmp_path):
    fsm, robot, registry = make_mission(scene)
    bleached = set(scene.ids("BLEACHED"))
    summary = fsm.run()

    assert summary.final_state == MissionState.MISSION_COMPLETE.value
    assert set(summary.treated) == bleached
    assert summary.skipped == {}
    for cid in bleached:
        e = registry.get(cid)
        assert e.health_status == "TREATED" and e.sampled_or_restored
        assert e.optimal_graft_pose_world is not None
    # Dead and healthy colonies are never touched.
    for status in ("DEAD", "LIVE"):
        for cid in scene.ids(status):
            assert registry.get(cid).health_status == status
            assert not registry.get(cid).sampled_or_restored

    # Each fragment was placed on top of its colony.
    assert len(robot.placements) == len(bleached)
    restored_by_pose = {registry.get(c).optimal_graft_pose_world.position: c for c in bleached}
    for _, pose in robot.placements:
        e = registry.get(restored_by_pose[pose.position])
        top = e.position_world[2] + e.bounding_box_extent[2] / 2
        assert np.hypot(pose.position[0] - e.position_world[0], pose.position[1] - e.position_world[1]) < 0.05
        assert abs(pose.position[2] - top) < 0.03

    assert not robot.locked and robot.holding is None
    assert_log_well_formed(fsm.log)
    a = actions(fsm.log)
    assert a[0] == "mission_start" and a[-1] == "mission_complete"
    assert a.count("transplant_fragment") == len(bleached)

    path = tmp_path / "log.jsonl"
    fsm.log.save(str(path))
    reloaded = DecisionLog.load(str(path))
    assert [e.action for e in reloaded.entries] == a


def test_transition_evidence_is_real(scene):
    fsm, robot, registry = make_mission(scene)
    fsm.run()
    by_action = {}
    for e in fsm.log.entries:
        by_action.setdefault(e.action, e)
    pick = by_action["select_pair"].evidence
    c = pick["chosen"]
    w = FSMConfig().weights
    assert c["J"] == pytest.approx(w.w1 * c["travel"] + w.w2 * c["transfer"] - w.w3 * c["health"], abs=1e-4)
    graft = by_action["transplant_fragment"].evidence
    assert graft["observations"][0]["n_points"] > 100
    assert graft["chosen"]["surface_normal"][2] > 0.866
    assert graft["ik_results"][-1]["reachable"] is True
    nav = by_action["arrive_donor"].evidence["navigation"]
    assert nav["residual_m"] <= FSMConfig().nav.position_tolerance


def test_survey_with_perceiver_builds_registry_then_restores(scene):
    fsm, robot, registry = make_mission(scene, survey=True)
    summary = fsm.run()
    assert summary.final_state == "MISSION_COMPLETE"
    assert {e.cluster_id for e in registry.all()} == {e.cluster_id for e in scene.entries}
    assert set(summary.treated) == set(scene.ids("BLEACHED"))
    assert "survey_waypoint" in actions(fsm.log) and "survey_complete" in actions(fsm.log)
    assert_log_well_formed(fsm.log)


def test_deterministic_with_seed():
    def run():
        fsm, _, _ = make_mission(generate_scene(seed=3))
        fsm.run()
        return [(e.state, e.action, json.dumps(e.evidence, sort_keys=True), e.outcome) for e in fsm.log.entries]

    assert run() == run()


def test_unseeded_live_scene_runs():
    scene = generate_scene(seed=None)
    fsm, _, _ = make_mission(scene)
    summary = fsm.run()
    assert summary.final_state == "MISSION_COMPLETE"
    assert set(summary.treated) == set(scene.ids("BLEACHED"))


# ----------------------------------------------------- adaptation / failures


def test_fragment_dislodged_mid_carry_is_reacquired(scene):
    fsm, robot, registry = make_mission(scene)
    fired = []

    def director(f: MissionFSM) -> None:
        if not fired and f.state == MissionState.NAVIGATE_TO_RECIPIENT:
            robot.schedule_dislodge(after_ticks=5)
            fired.append(f.recipient_id)

    summary = fsm.run(on_step=director)
    assert fired
    assert summary.final_state == "MISSION_COMPLETE"
    assert set(summary.treated) == set(scene.ids("BLEACHED"))
    assert summary.memory["dislodge_events"] == 1
    a = actions(fsm.log)
    i = a.index("fragment_dislodged")
    ev = fsm.log.entries[i].evidence
    assert ev["navigation"]["fragment_held"] is False
    assert ev["next_state"] == "COMPUTE_RESTORATION_PLAN"
    assert a[i + 1] == "select_pair" and a[i + 3] == "harvest_fragment"  # re-acquire
    assert_log_well_formed(fsm.log)


def test_new_bleached_colony_mid_mission_is_treated(scene):
    fsm, robot, registry = make_mission(scene)
    known = registry.get(scene.ids("BLEACHED")[0])
    added = []

    def director(f: MissionFSM) -> None:
        if not added and "transplant_fragment" in actions(f.log):
            e = scene.add_cluster("cluster_new", known.species_class, "BLEACHED", 0.4, free_spot(scene), genet_id=known.genet_id)
            registry.upsert(e)
            added.append(e.cluster_id)

    summary = fsm.run(on_step=director)
    assert added
    assert "cluster_new" in summary.treated
    assert set(summary.treated) == set(scene.ids("BLEACHED"))


def test_one_ik_failure_at_the_rack_is_retried(scene):
    fsm, robot, _ = make_mission(scene)
    robot.ik_fail_next = 1
    summary = fsm.run()
    assert "abstain_harvest" not in actions(fsm.log)
    assert set(summary.treated) == set(scene.ids("BLEACHED"))


def test_rack_that_stays_unreachable_is_rejected(scene):
    fsm, robot, _ = make_mission(scene)
    robot.ik_fail_next = 2
    summary = fsm.run()
    a = actions(fsm.log)
    i = a.index("abstain_harvest")
    assert [r["reachable"] for r in fsm.log.entries[i].evidence["ik_results"]] == [False, False]
    assert "IK unreachable" in fsm.log.entries[i].outcome
    assert summary.memory["donor_rejections"]
    assert a[i + 1] in ("select_pair", "mission_complete")
    assert summary.final_state == "MISSION_COMPLETE"
    assert all("rejected" in reason for reason in summary.skipped.values())


def test_unsuitable_site_is_rejected_and_remembered(scene):
    target = scene.ids("BLEACHED")[0]
    scene.make_pillar(target)
    fsm, robot, registry = make_mission(scene)
    summary = fsm.run()
    assert summary.final_state == "MISSION_COMPLETE"
    assert target in summary.skipped
    assert "patch" in summary.skipped[target] or "points" in summary.skipped[target]
    assert set(summary.treated) == set(scene.ids("BLEACHED")) - {target}
    # Never retried after rejection.
    assert sum(1 for e in fsm.log.entries if e.action == "abstain_transplant") == 1
    assert robot.holding is None  # carried fragment went to another colony or back to the station


def test_genet_not_in_stock_is_skipped(scene):
    station = scene.base_station()
    scene.add_cluster("orphan", "species_x", "BLEACHED", 0.3, free_spot(scene), genet_id="unstocked")
    fsm, _, _ = make_mission(scene, station=station)
    summary = fsm.run()
    assert summary.final_state == "MISSION_COMPLETE"
    assert "not in stock" in summary.skipped["orphan"]


def test_colony_without_a_genet_match_is_never_touched(scene):
    scene.add_cluster("unknown", "species_x", "BLEACHED", 0.3, free_spot(scene))
    fsm, robot, registry = make_mission(scene)
    summary = fsm.run()
    assert summary.skipped["unknown"] == "no confident UV genet match"
    assert registry.get("unknown").health_status == "BLEACHED"


def test_dead_colonies_are_reported_as_ignored(scene):
    fsm, _, _ = make_mission(scene)
    fsm.run()
    assert set(fsm.log.entries[-1].evidence["ignored_dead"]) == set(scene.ids("DEAD"))


def test_stock_runs_out_and_later_colonies_are_skipped(scene):
    registry_entries = [e for e in scene.entries if e.genet_id]
    genet = registry_entries[0].genet_id
    same = [e.cluster_id for e in registry_entries if e.genet_id == genet]
    assert len(same) >= 2
    station = scene.base_station()
    while station.available(genet) > 1:
        station.take(genet)
    fsm, _, _ = make_mission(scene, station=station)
    summary = fsm.run()
    assert station.available(genet) == 0
    assert sum(cid in summary.treated for cid in same) == 1
    assert sum("not in stock" in summary.skipped.get(cid, "") for cid in same) == len(same) - 1


def test_lost_contact_fails_the_push_test(scene):
    fsm, robot, registry = make_mission(scene)
    fsm.placement_verifier = lambda pose: {"stable": True, "contact": False}
    summary = fsm.run()
    assert summary.treated == []
    assert "placement_unstable" in actions(fsm.log)
    assert all(registry.get(c).health_status == "BLEACHED" for c in scene.ids("BLEACHED"))


@pytest.mark.parametrize("day,observation,expected", [
    (7, {"contact_maintained": True, "symbiont_density_pct_of_healthy": 45}, "TREATED"),
    (7, {"contact_maintained": False, "symbiont_density_pct_of_healthy": 2}, "NOT_RECOVERED"),
    (56, {"contact_maintained": True, "symbiont_density_pct_of_healthy": 95}, "RECOVERED"),
    (56, {"contact_maintained": True, "symbiont_density_pct_of_healthy": 5}, "NOT_RECOVERED"),
])
def test_return_visit_decisions(scene, day, observation, expected):
    fsm, _, registry = make_mission(scene)
    fsm.run()
    results = fsm.revisit(day, lambda entry, d: observation)
    assert set(results) == set(scene.ids("BLEACHED"))
    assert set(results.values()) == {expected}
    assert registry.get(scene.ids("BLEACHED")[0]).health_status == expected
    assert_log_well_formed(fsm.log)


def test_return_visit_skips_colonies_already_decided(scene):
    fsm, _, _ = make_mission(scene)
    fsm.run()
    fsm.revisit(7, lambda entry, d: {"contact_maintained": False})
    assert fsm.revisit(56, lambda entry, d: {"contact_maintained": True}) == {}


def test_weak_donor_abstention(scene):
    cfg = FSMConfig(min_donor_health=0.99)  # every donor below threshold
    fsm, robot, _ = make_mission(scene, config=cfg)
    summary = fsm.run()
    assert summary.treated == []
    assert robot.ticks == 0  # never moved
    ev = fsm.log.entries[-1].evidence
    assert ev["skipped"] and all("health_score" in s["reason"] for s in ev["skipped"])


def test_patched_weights_still_pass(scene):
    """Shape of an Argon-proposed patch: a config diff run through the same suite."""
    patched = FSMConfig.from_dict({**FSMConfig().to_dict(), "weights": {"w1": 1.0, "w2": 1.5, "w3": 4.0}})
    fsm, _, _ = make_mission(scene, config=patched)
    summary = fsm.run()
    assert set(summary.treated) == set(scene.ids("BLEACHED"))


# ------------------------------------------------------------ sample output


def run_showcase(seed: int = 0):
    """Survey + one unsuitable site + one dislodge mid-carry: the sample log
    handed to the dashboard and cloud-debrief branches."""
    scene = generate_scene(seed=seed)
    scene.make_pillar(scene.ids("BLEACHED")[-1])
    fsm, robot, registry = make_mission(scene, survey=True)
    fsm.placement_verifier = robot.verify_placement
    fired = []

    def director(f: MissionFSM) -> None:
        if not fired and f.state == MissionState.NAVIGATE_TO_RECIPIENT and f.memory.harvest_counts:
            robot.schedule_dislodge(after_ticks=8)
            fired.append(True)

    summary = fsm.run(on_step=director)
    return fsm, registry, summary


def test_showcase_run():
    fsm, _, summary = run_showcase()
    assert summary.final_state == "MISSION_COMPLETE"
    assert summary.memory["dislodge_events"] == 1
    assert len(summary.skipped) == 1
    assert_log_well_formed(fsm.log)


if __name__ == "__main__":
    import argparse
    import dataclasses

    parser = argparse.ArgumentParser(description="Run the showcase mock mission and save its outputs.")
    parser.add_argument("--out", default="agent/samples", help="output directory")
    parser.add_argument("--seed", type=int, default=0)
    args = parser.parse_args()
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    fsm, registry, summary = run_showcase(args.seed)
    fsm.log.save(str(out / "decision_log_sample.jsonl"))
    (out / "registry_sample.json").write_text(json.dumps(registry.dump(), indent=1))
    (out / "summary_sample.json").write_text(json.dumps(dataclasses.asdict(summary), indent=1))
    print(json.dumps(dataclasses.asdict(summary), indent=1))
    print(f"{len(fsm.log.entries)} log entries -> {out}")
