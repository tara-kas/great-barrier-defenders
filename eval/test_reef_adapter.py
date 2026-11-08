"""End-to-end team FSM checks against the actual offline reef adapter.

These tests inspect the saved native geometry and continuous object poses,
not mock graft points or a scripted list of expected mission states.
"""
import contextlib
import io
import math
from pathlib import Path
import sys

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "sim" / "pelagic"), str(ROOT)]
from scripts.plan_team_demo import plan
from reefsim.inspection import auto_inspection_mode
from reefsim.natural_contact import closest_point_on_triangle
from reefsim.scanned_fragment import split_scanned_donor
from reefsim.team_physics import dropped_step, push_response


@pytest.fixture(scope="module")
def completed_reef_mission(tmp_path_factory):
    output = tmp_path_factory.mktemp("reef-adapter-mission")
    with contextlib.redirect_stdout(io.StringIO()):
        robot, report = plan(output)
    assert (output / "trace.json.gz").exists()
    return robot, report


def fragment_frames(robot):
    identifier = robot.active_fragment["id"]
    for snapshot in robot.frames:
        fragment = next(f for f in snapshot["fragments"] if f["id"] == identifier)
        yield snapshot, fragment, snapshot["robots"][1]


def rotated(point, yaw):
    x, y, z = point
    c, s = math.cos(yaw), math.sin(yaw)
    return (c*x-s*y, s*x+c*y, z)


def test_team_controller_completes_one_harvest_with_same_id_loss_recovery(completed_reef_mission):
    robot, report = completed_reef_mission
    assert report["summary"]["final_state"] == "MISSION_COMPLETE"
    assert len(report["summary"]["treated"]) == 1
    assert report["summary"]["unverified_placements"] == []
    events = {kind: [e for e in report["audit"] if e["event"] == kind]
              for kind in ("harvest", "fragment_lost", "recovered", "placed", "push_test")}
    assert all(len(rows) == 1 for rows in events.values())
    identifier = events["harvest"][0]["fragment_id"]
    assert all(rows[0]["fragment_id"] == identifier for rows in events.values())
    assert events["recovered"][0]["same_fragment"]
    assert sum(c["harvested_fragments"] for c in robot.sim.corals) == 1
    assert robot.active_fragment["stage"] == "placed"
    assert robot.recipient["health"] == "bleached_alive"
    assert robot.recipient["task_status"] == "verified"
    assert report["model_calls"] == 0
    assert "offline demo" in report["sensor_mode"]


def test_uv_detection_precedes_harvest_and_is_off_for_all_later_operations(completed_reef_mission):
    robot, report = completed_reef_mission
    harvest = next(e for e in report["audit"] if e["event"] == "harvest")
    scans = [e for e in report["audit"] if e["event"] in ("uv_donor", "uv_recipient")]
    assert {e["event"] for e in scans} == {"uv_donor", "uv_recipient"}
    assert all(e["accepted"] and e["timestamp"] < harvest["time"] for e in scans)
    assert {e["health"] for e in scans} == {"healthy", "bleached_alive"}
    inspected = set()
    for snapshot, fragment, worker in fragment_frames(robot):
        mode = auto_inspection_mode(worker["state"], carrying=worker["carrying"])
        if mode == "uv":
            inspected.add(worker["scan_target_id"])
        if snapshot["time"] >= harvest["time"]:
            assert mode == "white", (snapshot["time"], worker["state"], fragment["stage"])
    assert {robot.source["id"], robot.recipient["id"]} <= inspected


def test_native_grasp_pose_is_continuous_at_harvest_recovery_and_release(completed_reef_mission):
    robot, _ = completed_reef_mission
    previous = None
    seen = set()
    for snapshot, fragment, worker in fragment_frames(robot):
        if fragment["stage"] == "carried":
            offset = rotated(fragment["grasp_point"], fragment["yaw"])
            expected = [fragment["base_world"][k]+offset[k] for k in range(3)]
            assert math.dist(expected, worker["gripper_world"]) < 1e-8
            heading=(worker['yaw']+worker.get('wrist_yaw',0.)-fragment['yaw'])%(2*math.pi)
            if 'grip_heading' not in locals(): grip_heading=heading
            assert abs((heading-grip_heading+math.pi)%(2*math.pi)-math.pi)<1e-8, 'Coral rotated inside closed jaws'
        if previous:
            old_snapshot, old_fragment, _ = previous
            fragment_turn = abs((fragment["yaw"]-old_fragment["yaw"]+math.pi) % (2*math.pi)-math.pi)
            assert fragment_turn < .12, (snapshot["time"], "instant fragment rotation", fragment_turn)
            transition = old_fragment["stage"], fragment["stage"]
            if transition in (("attached_to_donor", "carried"), ("dropped", "carried"), ("carried", "placed")):
                seen.add(transition)
                # A smooth arm segment begins at the existing object pose.
                # Its first 50 ms cannot conceal a centimeter-scale teleport.
                assert math.dist(old_fragment["base_world"], fragment["base_world"]) < .005, (
                    transition, snapshot["time"], old_fragment["base_world"], fragment["base_world"])
        previous = snapshot, fragment, worker
    assert ("dropped", "carried") in seen
    assert ("carried", "placed") in seen


def test_placement_uses_actual_living_tissue_and_existing_recipient_triangle(completed_reef_mission):
    robot, _ = completed_reef_mission
    fragment, donor, recipient = robot.active_fragment, robot.source, robot.recipient
    part = split_scanned_donor(donor["radius"], donor["height"], fragment["source_mesh_seed"],
                              slots=donor["scanned_partition_slots"], detail=fragment["source_mesh_detail"])["fragments"][fragment["source_slot"]]
    fixture = recipient["contact_fixture"]
    index = fixture["natural_fragment_contact_index"]
    assert index < len(part["mesh"]["source_vertex_indices"]), "Synthetic skeleton cap is not living tissue"
    local = part["mesh"]["points"][index]
    low, high = fragment["contact_band_local_z"]
    assert low <= local[2] <= high, "Contact must be above the severed skeleton edge"
    offset = rotated(local, fragment["yaw"])
    world = [fragment["base_world"][k]+offset[k] for k in range(3)]
    nearest = closest_point_on_triangle(world, *fixture["contact_triangle_world"])
    assert math.dist(world, nearest) <= .0015
    assert math.dist(world, recipient["contact_point"]) <= .0015
    # The entire cutting must stay on the outward side of its supporting
    # tangent plane; selecting an interior-band point alone is insufficient.
    normal = recipient["contact_normal"]
    for point in part["mesh"]["points"]:
        p = rotated(point, fragment["yaw"])
        signed = sum((p[k]+fragment["base_world"][k]-recipient["contact_point"][k])*normal[k] for k in range(3))
        assert signed >= -1e-7


def test_default_push_passes_but_weak_or_broken_attachment_fails(completed_reef_mission):
    _, report = completed_reef_mission
    measured = report["push_tests"][0]
    assert measured["stable"] and measured["contact"] and not measured["broken"]
    assert measured["force_n"] > 0
    assert 0 < measured["peak_displacement_m"] < .0015
    broken = push_response(force=.18, break_force=.10)
    assert broken["broken"] and not broken["stable"]
    assert broken["peak_displacement_m"] > .002
    weak = push_response(stiffness=5.)
    assert not weak["stable"] and weak["peak_displacement_m"] > .002


def test_settled_dropped_coral_stays_on_bed_while_gripper_reaches_it():
    position, velocity = [1., 2., .025], [0., 0., 0.]
    for _ in range(100):
        position, velocity = dropped_step(position, velocity, [.10, .035, 0.], .05)
    assert position == pytest.approx([1., 2., .025], abs=1e-8)
    assert velocity == pytest.approx([0., 0., 0.], abs=1e-8)


def test_carried_replan_preserves_identity_and_requires_prior_uv_approval(completed_reef_mission):
    from agent.base_station import Rack
    from perception.registry import SemanticMapEntry
    from reefsim.team_adapter import ReefRobotAdapter
    completed, _ = completed_reef_mission
    robot = ReefRobotAdapter(completed.sim.config, capture=False)
    donor = next(c for c in robot.sim.corals if c['donor_capacity'] and c['genet_id']=='R')
    target = next(c for c in robot.sim.corals if c['substrate_suitable'])
    fragment = next(f for f in robot.sim.fragments if f['donor_id']==donor['id'])
    fragment['stage']='carried'
    robot.source=donor
    robot.active_fragment=fragment
    robot.worker.update(carrying=True,fragment_id=fragment['id'])
    source=Rack(donor['id'],'R','pocillopora',0,.95,tuple(donor['position']),'living_reef',())
    entry=SemanticMapEntry(target['id'],'pocillopora','BLEACHED',.3,tuple(target['position']),(1.,1.,1.),genet_id='R')
    # No second UV inspection while carrying: hold until the already approved
    # recipient is available, rather than substituting donor inventory.
    assert robot.prepare_pair(entry,source)['allowed'] is False
    assert robot.active_fragment is fragment and robot.held_fragment_id()==fragment['id']
    robot.sim._detection_history.append({'accepted':True,'role':'recipient','coral_id':target['id']})
    assert robot.prepare_pair(entry,source)['allowed'] is True
    assert robot.active_fragment is fragment and fragment['target_id']==target['id']
    assert robot.can_return_fragment(source) is False


def test_push_approach_meets_push_motion_without_tool_snap(completed_reef_mission):
    robot, _ = completed_reef_mission
    boundaries = []
    for before, after in zip(robot.frames, robot.frames[1:]):
        first, second = before['robots'][1], after['robots'][1]
        if first['state'] == 'PUSH_APPROACH' and second['state'] == 'PUSH_TEST':
            boundaries.append(math.dist(first['gripper_world'], second['gripper_world']))
    assert len(boundaries) == 1
    assert boundaries[0] < .002, 'Push test jumped from its approach endpoint'
