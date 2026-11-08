"""Contract tests for living sources and persistent-object recovery (mock physics)."""

import dataclasses

import pytest

from agent.base_station import BaseStation, Rack
from agent.fsm import MissionFSM, MissionState
from agent.graft_point import GraftCandidate
from agent.pairing import plan_pairs
from eval.mock_robot import MockRobotInterface
from eval.synthetic_scene import generate_scene
from perception.registry import SemanticSeabedRegistry


class ReefRobot(MockRobotInterface):
    """Deliberately synthetic adapter for testing the optional capability protocol."""

    recovery_identity = "fragment-1"
    permit_donor = True
    permit_recipient = True

    def __post_init__(self):
        super().__post_init__()
        self.events = []

    def prepare_pair(self, recipient, source):
        self.events.append("recipient_uv")
        return {"allowed": self.permit_recipient, "source": "test fixture"}

    def inspect_donor(self, source, recipient):
        self.events.append("donor_uv")
        return {"allowed": self.permit_donor, "source": "test fixture"}

    def attach_fragment(self, cluster_id):
        self.events.append("harvest")
        super().attach_fragment(self.recovery_identity)

    def held_fragment_id(self):
        return self.holding

    def recover_lost_fragment(self, fragment_id, recipient_id):
        self.events.append("recover")
        self.holding = self.recovery_identity
        return {"recovered": True, "fragment_id": self.recovery_identity}

    def contact_candidate(self, entry):
        self.events.append("contact_candidate")
        x, y, z = entry.position_world
        z += entry.bounding_box_extent[2] / 2
        candidate = GraftCandidate((x, y, z), (0, 0, 0, 1), (0, 0, 1), 30, 1.0)
        return candidate, {"source": "test fixture, not natural mesh evidence"}

    def detach_fragment(self, pose):
        self.events.append("release")
        super().detach_fragment(pose)

    def verify_placement(self, pose):
        self.events.append("push_test")
        return super().verify_placement(pose)


def setup_mission():
    scene = generate_scene(seed=0)
    recipient = next(e for e in scene.entries if e.health_status == "BLEACHED")
    source = Rack("living-donor", recipient.genet_id, recipient.species_class, 1, .95,
                  (1.0, 1.0, .2), "living_reef", ("fragment-1",))
    station = BaseStation((99, 99, 99), [source])  # Navigation must never use this fallback.
    registry = SemanticSeabedRegistry()
    registry.upsert(recipient)
    robot = ReefRobot(scene)
    fsm = MissionFSM(robot, registry, base_station=station, wait=robot.advance,
                     fragment_held=robot.fragment_held, placement_verifier=robot.verify_placement)
    return fsm, robot, station, recipient


def test_same_fragment_recovery_does_not_take_another_living_cutting():
    fsm, robot, station, recipient = setup_mission()
    fired = []

    def drop_once(current):
        if not fired and current.state == MissionState.NAVIGATE_TO_RECIPIENT:
            robot.schedule_dislodge(after_ticks=1)
            fired.append(True)

    result = fsm.run(on_step=drop_once)
    assert result.final_state == "MISSION_COMPLETE"
    assert result.treated == [recipient.cluster_id]
    assert station.stock() == {recipient.genet_id: 0}
    assert result.memory["harvest_counts"] == {"living-donor": 1}
    assert robot.events == ["recipient_uv", "donor_uv", "harvest", "recover",
                            "contact_candidate", "release", "push_test"]
    recovered = next(e for e in fsm.log.entries if e.action == "recover_fragment")
    assert recovered.evidence["same_fragment"] is True
    assert recovered.evidence["fragment_id"] == "fragment-1"
    nav = next(e for e in fsm.log.entries if e.action == "arrive_donor")
    assert nav.evidence["navigation"]["target"] == pytest.approx([1.0, 1.0, .55])


def test_recovery_cannot_replace_persistent_object_with_a_different_fragment():
    fsm, robot, _, _ = setup_mission()
    while fsm.state != MissionState.NAVIGATE_TO_RECIPIENT:
        fsm.step()
    robot.holding = None
    robot.recovery_identity = "replacement-impostor"
    result = fsm.run()
    assert result.final_state == "ABORTED"
    assert result.treated == []
    assert robot.events.count("harvest") == 1
    assert fsm.log.entries[-1].action == "recovery_failed"


@pytest.mark.parametrize("which", ["donor", "recipient"])
def test_failed_preharvest_uv_check_cannot_consume_living_coral(which):
    fsm, robot, station, recipient = setup_mission()
    setattr(robot, f"permit_{which}", False)
    assert fsm.run().treated == []
    assert "harvest" not in robot.events
    assert station.available(recipient.genet_id) == 1


def test_push_test_rejection_does_not_mark_recipient_treated():
    fsm, robot, _, _ = setup_mission()
    robot.unstable_next = 1
    assert fsm.run().treated == []
    assert any(e.action == "placement_unstable" for e in fsm.log.entries)


def test_multiple_living_sources_use_their_own_positions_and_stock():
    _, _, _, recipient = setup_mission()
    far = Rack("far", recipient.genet_id, recipient.species_class, 2, .9,
               (50, 50, 0), "living_reef", ("far-1", "far-2"))
    near = dataclasses.replace(far, slot="near", position_world=(1, 1, 0),
                               fragments_available=1, fragment_ids=("near-1",))
    station = BaseStation((0, 0, 0), [far, near])
    plan = plan_pairs([recipient], (0, 0, 0), station)
    assert plan.best.donor_id == "near"
    station.take(recipient.genet_id, "near", "near-1")
    assert station.available(recipient.genet_id) == 2
    assert plan_pairs([recipient], (0, 0, 0), station).best.donor_id == "far"
    station.put_back(recipient.genet_id, "near", "near-1")
    assert station.rack_for(recipient.genet_id, "near").fragment_ids == ("near-1",)


def test_same_genet_with_different_species_is_rejected():
    _, _, _, recipient = setup_mission()
    station = BaseStation((0, 0, 0), [Rack("bad", recipient.genet_id, "other-species", 1, .95)])
    assert plan_pairs([recipient], (0, 0, 0), station).best is None


def test_no_valid_return_fixture_stops_and_retains_original_fragment():
    fsm, robot, station, recipient = setup_mission()
    queried_sources = []
    robot.can_return_fragment = lambda source: queried_sources.append(source.slot) or False
    while fsm.state != MissionState.NAVIGATE_TO_RECIPIENT:
        fsm.step()
    original_fragment = robot.held_fragment_id()
    # A changed recipient leaves nowhere validated to put the carried cutting.
    fsm.registry.upsert(dataclasses.replace(recipient, health_status="DEAD"))
    summary = fsm.run()
    assert summary.final_state == "ABORTED"
    assert queried_sources == ["living-donor"]
    assert robot.held_fragment_id() == original_fragment == "fragment-1"
    assert fsm.fragment_id == original_fragment and fsm.carrying == recipient.genet_id
    assert robot.locked and not robot.velocity.any()
    assert "release" not in robot.events
    assert station.available(recipient.genet_id) == 0
    assert fsm.log.entries[-1].action == "abort_no_return_fixture"
    assert fsm.log.entries[-1].outcome == "no validated return fixture; retaining fragment safely"
