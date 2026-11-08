"""MissionFSM: the on-device mission loop.

    SURVEY_SEABED -> COMPUTE_RESTORATION_PLAN -> NAVIGATE_TO_DONOR (the base station) ->
    HARVEST_FRAGMENT -> NAVIGATE_TO_RECIPIENT -> TRANSPLANT_FRAGMENT
         ^                                                   |
         +------------- loop back to COMPUTE_RESTORATION_PLAN+

Drives any `RobotInterface` (mock or Isaac Sim adapter) identically. No network
calls, no model calls: it consumes the registry that perception fills.
Every transition is logged with the evidence that caused it.

Pluggable dependencies (all optional except robot and registry):
- `wait(dt)`: advances time between control ticks (mock.advance, or the sim
  adapter's step). Defaults to time.sleep.
- `perceiver(frame, pose) -> [SemanticMapEntry]`: hull-camera detector from
  the perception branch. Without one, survey uses the pre-populated registry.
  It raises `PerceptionFailure` when a frame could not be processed, and may
  expose `last_evidence` to have its reasoning logged with each survey frame.
- `fragment_held() -> bool`: gripper force/camera check for dislodgement.
- `placement_verifier(pose) -> {"stable": bool, "contact": bool, ...}`: post-placement
  push test. Symbiont transfer needs the fragment to stay touching the colony.

Optional robot capabilities leave the frozen RobotInterface ABC unchanged:
`prepare_pair(recipient, source)`, `inspect_donor(source, recipient)`, and
`inspect_recipient(recipient)` return evidence dictionaries with an `allowed`
flag. They run before harvesting or releasing. `held_fragment_id()` and
`recover_lost_fragment(fragment_id, recipient_id)` preserve the identity of a
dropped object; recovery returns `{recovered, fragment_id, ...}` and still
requires the independent fragment monitor. `contact_candidate(entry)` returns
`(GraftCandidate | None, evidence)` for measured natural contact surfaces.
`navigation_pose(entry_or_source, purpose=...)` supplies body stand-off poses;
`get_sim_time()` and `on_fsm_transition(state_name)` synchronize recording.
`can_return_fragment(source)` may refuse an unvalidated return fixture; the FSM
then stops and retains the fragment rather than releasing it at a living donor.
"""

from __future__ import annotations

import dataclasses
import time
from collections import Counter
from dataclasses import dataclass
from enum import Enum
from typing import Any, Callable, Optional

import numpy as np

from agent.base_station import BaseStation
from agent.config import FSMConfig, GraftConfig
from agent.decision_log import DecisionLog
from agent.evidence import entry_summary, pose_summary, to_jsonable
from agent.geometry import bbox_top, box_mask, distance, frame_to_world_points
from agent.graft_point import GraftCandidate, select_graft_candidates
from agent.memory import EpisodicMemory
from agent.pairing import best_recipient_for_carried, is_open_recipient, plan_pairs
from agent.robot_interface import Pose, RGBDFrame, RobotInterface
from perception.registry import SemanticMapEntry, SemanticSeabedRegistry

Perceiver = Callable[[RGBDFrame, Pose], list[SemanticMapEntry]]


class MissionState(str, Enum):
    SURVEY_SEABED = "SURVEY_SEABED"
    COMPUTE_RESTORATION_PLAN = "COMPUTE_RESTORATION_PLAN"
    NAVIGATE_TO_DONOR = "NAVIGATE_TO_DONOR"
    HARVEST_FRAGMENT = "HARVEST_FRAGMENT"
    RECOVER_FRAGMENT = "RECOVER_FRAGMENT"
    NAVIGATE_TO_RECIPIENT = "NAVIGATE_TO_RECIPIENT"
    TRANSPLANT_FRAGMENT = "TRANSPLANT_FRAGMENT"
    RETURN_VISIT = "RETURN_VISIT"
    MISSION_COMPLETE = "MISSION_COMPLETE"
    ABORTED = "ABORTED"


TERMINAL = {MissionState.MISSION_COMPLETE, MissionState.ABORTED}


class PerceptionFailure(RuntimeError):
    """A survey frame could not be processed, as opposed to showing no coral."""


@dataclass
class MissionSummary:
    final_state: str
    steps: int
    sim_time_s: float
    treated: list[str]
    skipped: dict[str, str]
    memory: dict[str, Any]
    unverified_placements: list[str] = dataclasses.field(default_factory=list)


def assess_revisit(day: int, final_day: int, observation: dict, recovered_density_pct: float) -> str:
    """Status after a return visit. Recovery is only judged at the last visit."""
    if not observation.get("contact_maintained", False):
        return "NOT_RECOVERED"
    if day < final_day:
        return "TREATED"
    density = observation.get("symbiont_density_pct_of_healthy", 0)
    return "RECOVERED" if density >= recovered_density_pct else "NOT_RECOVERED"


def lawnmower(bounds: tuple[float, float, float, float], swath: float, z: float) -> list[tuple[float, float, float]]:
    xmin, xmax, ymin, ymax = bounds
    ys = np.arange(ymin + swath / 2.0, ymax, swath)
    xs = np.arange(xmin + swath / 2.0, xmax, swath)
    out = []
    for i, y in enumerate(ys):
        row = xs if i % 2 == 0 else xs[::-1]
        out.extend((float(x), float(y), float(z)) for x in row)
    return out


class MissionFSM:
    def __init__(
        self,
        robot: RobotInterface,
        registry: SemanticSeabedRegistry,
        *,
        base_station: BaseStation,
        config: FSMConfig = FSMConfig(),
        log: Optional[DecisionLog] = None,
        wait: Callable[[float], None] = time.sleep,
        perceiver: Optional[Perceiver] = None,
        fragment_held: Optional[Callable[[], bool]] = None,
        placement_verifier: Optional[Callable[[Pose], dict]] = None,
    ) -> None:
        self.robot = robot
        self.registry = registry
        self.station = base_station
        self.config = config
        self.log = log if log is not None else DecisionLog()
        self.wait = wait
        self.perceiver = perceiver
        self.fragment_held = fragment_held
        self.placement_verifier = placement_verifier

        self.state = MissionState.SURVEY_SEABED
        self.memory = EpisodicMemory(config.max_attempts_per_recipient)
        self.steps = 0
        self.sim_time = 0.0
        self.genet_id: Optional[str] = None  # genet of the current pairing
        self.recipient_id: Optional[str] = None
        self.donor_id: Optional[str] = None
        self.fragment_id: Optional[str] = None
        self._lost_genet: Optional[str] = None
        self.carrying: Optional[str] = None  # genet of the fragment in the gripper
        self.returning = False  # carrying a fragment back to the station (no recipient left)
        self.skipped: dict[str, str] = {}
        self._started = False
        self._survey_queue: Optional[list[tuple[float, float, float]]] = None
        self._perception_failures = 0
        self._failed_waypoints: list[tuple[float, float, float]] = []
        self._unverified: list[str] = []
        self._handlers: dict[MissionState, Callable[[], MissionState]] = {
            MissionState.SURVEY_SEABED: self._survey,
            MissionState.COMPUTE_RESTORATION_PLAN: self._plan,
            MissionState.NAVIGATE_TO_DONOR: self._navigate_to_donor,
            MissionState.HARVEST_FRAGMENT: self._harvest,
            MissionState.RECOVER_FRAGMENT: self._recover_fragment,
            MissionState.NAVIGATE_TO_RECIPIENT: self._navigate_to_recipient,
            MissionState.TRANSPLANT_FRAGMENT: self._transplant,
        }

    # ------------------------------------------------------------------ driver

    @property
    def done(self) -> bool:
        return self.state in TERMINAL

    def step(self) -> MissionState:
        """Run one state handler. Registry changes between steps are picked up."""
        if not self._started:
            self._started = True
            self._go(
                MissionState.SURVEY_SEABED,
                "mission_start",
                {
                    "config": self.config.to_dict(),
                    "registry": [entry_summary(e) for e in self.registry.all()],
                    "perceiver": self.perceiver is not None,
                    "fragment_monitor": self.fragment_held is not None,
                    "placement_verifier": self.placement_verifier is not None,
                },
            )
        if self.done:
            return self.state
        self.state = self._handlers[self.state]()
        self.steps += 1
        return self.state

    def run(self, max_steps: int = 1000, on_step: Optional[Callable[["MissionFSM"], None]] = None) -> MissionSummary:
        """Step until terminal. `on_step` runs between steps (perturbation director, dashboard)."""
        while not self.done and self.steps < max_steps:
            self.step()
            if on_step is not None:
                on_step(self)
        if not self.done:
            self.state = self._go(MissionState.ABORTED, "abort", {"steps": self.steps}, f"max_steps {max_steps} reached")
        return self.summary()

    def summary(self) -> MissionSummary:
        entries = self.registry.all()
        treated = sorted(e.cluster_id for e in entries if e.sampled_or_restored)
        skipped = {}
        for cid in sorted(e.cluster_id for e in entries if is_open_recipient(e)):
            reasons = self.memory.recipient_rejections.get(cid)
            skipped[cid] = reasons[-1] if reasons else self.skipped.get(cid, "not processed")
        return MissionSummary(
            final_state=self.state.value,
            steps=self.steps,
            sim_time_s=round(self.sim_time, 3),
            treated=treated,
            skipped=skipped,
            memory=self.memory.to_dict(),
            unverified_placements=sorted(self._unverified),
        )

    def _go(self, next_state: MissionState, action: str, evidence: dict, outcome: str = "ok") -> MissionState:
        clock = getattr(self.robot, "get_sim_time", None)
        if callable(clock):
            self.sim_time = float(clock())
        evidence = {
            **evidence,
            "next_state": next_state.value,
            "rov_pose": pose_summary(self.robot.get_pose()),
            "sim_time_s": round(self.sim_time, 3),
            "carrying": self.carrying,
            "fragment_id": self.fragment_id,
        }
        self.log.record(self.state.value, action, to_jsonable(evidence), outcome)
        transition = getattr(self.robot, "on_fsm_transition", None)
        if callable(transition):
            transition(next_state.value)
        return next_state

    # ------------------------------------------------------------------ states

    def _survey(self) -> MissionState:
        cfg = self.config
        if self.perceiver is None:
            entries = self.registry.all()
            return self._go(
                MissionState.COMPUTE_RESTORATION_PLAN,
                "survey_registry_only",
                {
                    "source": "pre-populated registry (no perceiver injected)",
                    "n_entries": len(entries),
                    "counts_by_status": dict(Counter(e.health_status for e in entries)),
                },
            )
        if self._survey_queue is None:
            self._survey_queue = lawnmower(cfg.survey_bounds, cfg.survey_swath, cfg.seabed_z + cfg.hull_altitude)
        if not self._survey_queue:
            entries = self.registry.all()
            return self._go(
                MissionState.COMPUTE_RESTORATION_PLAN,
                "survey_complete",
                {
                    "n_entries": len(entries),
                    "counts_by_status": dict(Counter(e.health_status for e in entries)),
                    "failed_waypoints": self._failed_waypoints,
                },
            )
        wp = self._survey_queue.pop(0)
        status, nav_ev = self._navigate(Pose(wp), carrying=False)
        if status != "arrived":
            return self._go(MissionState.SURVEY_SEABED, "survey_waypoint_skipped", {"navigation": nav_ev}, status)
        frame = self.robot.get_hull_rgbd()
        pose = self.robot.get_pose()
        try:
            detections = self.perceiver(frame, pose)
        except PerceptionFailure as err:
            return self._perception_failed(wp, nav_ev, err)
        self._perception_failures = 0
        new, updated, kept, merged = [], [], [], []
        for d in detections:
            result = self._merge_detection(d)
            {"new": new, "updated": updated, "kept": kept, "merged": merged}[result].append(d.cluster_id)
        depth = np.asarray(frame.depth, dtype=float)
        valid = np.isfinite(depth) & (depth > 0)
        return self._go(
            MissionState.SURVEY_SEABED,
            "survey_waypoint",
            {
                "waypoint": wp,
                "waypoints_left": len(self._survey_queue),
                "navigation": nav_ev,
                "hull_frame": {
                    "valid_depth_px": int(valid.sum()),
                    "depth_min_m": float(depth[valid].min()) if valid.any() else None,
                    "depth_max_m": float(depth[valid].max()) if valid.any() else None,
                },
                "detections": [entry_summary(d) for d in detections],
                "new": new,
                "updated": updated,
                "kept_restored_or_sampled": kept,
                "merged_by_perceiver": merged,
                "perception": getattr(self.perceiver, "last_evidence", None),
            },
        )

    def _perception_failed(self, wp, nav_ev: dict, err: PerceptionFailure) -> MissionState:
        """A failed frame is not an empty seabed: never let it pass as a clean survey."""
        self._perception_failures += 1
        self._failed_waypoints.append(wp)
        limit = self.config.max_perception_failures
        evidence = {
            "waypoint": wp,
            "navigation": nav_ev,
            "error": str(err),
            "consecutive_failures": self._perception_failures,
            "failure_limit": limit,
            "perception": getattr(self.perceiver, "last_evidence", None),
        }
        if self._perception_failures >= limit:
            return self._go(
                MissionState.ABORTED,
                "abort",
                evidence,
                f"perception unavailable: {self._perception_failures} consecutive frames failed",
            )
        return self._go(MissionState.SURVEY_SEABED, "survey_waypoint_failed", evidence, str(err))

    def _merge_detection(self, d: SemanticMapEntry) -> str:
        """Upsert a detection without undoing mission progress."""
        existing = self.registry.get(d.cluster_id)
        if existing is d:
            return "merged"  # the perceiver already wrote this exact entry
        if existing is None:
            self.registry.upsert(d)
            return "new"
        if existing.sampled_or_restored:
            return "kept"
        self.registry.upsert(d)
        return "updated"

    def _plan(self) -> MissionState:
        cfg = self.config
        rov = self.robot.get_pose().position
        entries = self.registry.all()

        if self.carrying is not None:
            source = self.station.rack_for(self.carrying, self.donor_id)
            found = best_recipient_for_carried(
                self.carrying, rov, entries, exclude=self.memory.excluded_recipients(),
                species_class=source.species_class if source else None,
            )
            if found is None:
                can_return = getattr(self.robot, "can_return_fragment", None)
                if callable(can_return) and not can_return(source):
                    self.robot.set_cmd_vel((0.0, 0.0, 0.0), (0.0, 0.0, 0.0))
                    self.robot.lock_base()
                    self.returning = False
                    return self._go(
                        MissionState.ABORTED,
                        "abort_no_return_fixture",
                        {"genet_id": self.carrying, "donor_id": self.donor_id,
                         "fragment_retained": True, "memory": self.memory.to_dict()},
                        "no validated return fixture; retaining fragment safely",
                    )
                self.returning = True
                return self._go(
                    MissionState.NAVIGATE_TO_RECIPIENT,
                    "return_fragment_to_station",
                    {
                        "genet_id": self.carrying,
                        "reason": "no open recipient of this genet left",
                        "memory": self.memory.to_dict(),
                    },
                )
            recipient, carry_dist = found
            self.recipient_id = recipient.cluster_id
            inspection = self._inspect("prepare_pair", recipient, source)
            if inspection is not None and not inspection.get("allowed", False):
                self.memory.reject_recipient(recipient.cluster_id, "recipient inspection rejected")
                return self._go(MissionState.COMPUTE_RESTORATION_PLAN, "abstain_pair", {"inspection": inspection})
            return self._go(
                MissionState.NAVIGATE_TO_RECIPIENT,
                "select_recipient_for_carried",
                {
                    "genet_id": self.carrying,
                    "recipient": entry_summary(recipient),
                    "carry_distance_m": carry_dist,
                    "inspection": inspection,
                    "memory": self.memory.to_dict(),
                },
            )

        plan = plan_pairs(
            entries,
            rov,
            self.station,
            cfg.weights,
            exclude_racks=self.memory.excluded_donors(),
            exclude_recipients=self.memory.excluded_recipients(),
            min_donor_health=cfg.min_donor_health,
        )
        for skip in plan.skipped:
            self.skipped[skip.recipient_id] = skip.reason
        plan_ev = {
            "weights": cfg.weights,
            "n_open_recipients": sum(1 for e in entries if is_open_recipient(e)),
            "skipped": plan.skipped,
            "ignored_dead": plan.ignored_dead,
            "stock": self.station.stock(),
            "excluded_recipients": sorted(self.memory.excluded_recipients()),
            "memory": self.memory.to_dict(),
        }
        best = plan.best
        if best is None:
            summary = self.summary()
            return self._go(
                MissionState.MISSION_COMPLETE,
                "mission_complete",
                {**plan_ev, "treated": summary.treated, "skipped_final": summary.skipped},
            )
        self.genet_id, self.recipient_id = best.genet_id, best.recipient_id
        self.donor_id = best.donor_id
        source = self.station.rack_for(best.genet_id, best.donor_id)
        inspection = self._inspect("prepare_pair", self.registry.get(best.recipient_id), source)
        if inspection is not None and not inspection.get("allowed", False):
            self.memory.reject_recipient(best.recipient_id, "recipient inspection rejected")
            return self._go(MissionState.COMPUTE_RESTORATION_PLAN, "abstain_pair", {"inspection": inspection})
        return self._go(
            MissionState.NAVIGATE_TO_DONOR,
            "select_pair",
            {
                **plan_ev,
                "chosen": best.cost,
                "genet_id": best.genet_id,
                "other_pairings": [p.cost for p in plan.pairings[1:6]],
                "rack": source,
                "inspection": inspection,
                "recipient": entry_summary(self.registry.get(best.recipient_id)),
            },
        )

    def _navigate_to_donor(self) -> MissionState:
        rack = self.station.rack_for(self.genet_id, self.donor_id)
        if rack is None or rack.fragments_available <= 0:
            return self._go(
                MissionState.COMPUTE_RESTORATION_PLAN,
                "replan_target_changed",
                {"genet_id": self.genet_id, "stock": self.station.stock()},
                "genet no longer in stock",
            )
        status, nav_ev = self._navigate(self._station_pose(), carrying=False)
        if status != "arrived":
            self.memory.reject_donor(rack.slot, f"navigation {status}")
            return self._go(MissionState.COMPUTE_RESTORATION_PLAN, "navigate_failed", {"navigation": nav_ev}, status)
        return self._go(MissionState.HARVEST_FRAGMENT, "arrive_donor", {"rack": rack, "navigation": nav_ev})

    def _harvest(self) -> MissionState:
        rack = self.station.rack_for(self.genet_id, self.donor_id)
        if rack is None or rack.fragments_available <= 0:
            return self._go(MissionState.COMPUTE_RESTORATION_PLAN, "replan_target_changed", {"donor_id": self.donor_id})
        inspection = self._inspect("inspect_donor", rack, self.registry.get(self.recipient_id))
        if inspection is not None and not inspection.get("allowed", False):
            self.memory.reject_donor(rack.slot, "donor inspection rejected")
            return self._go(MissionState.COMPUTE_RESTORATION_PLAN, "abstain_harvest", {"inspection": inspection})
        target = Pose(self.station.position_for(rack))
        ik_results = []
        self.robot.lock_base()
        try:
            for attempt in range(self.config.harvest_ik_attempts):
                reachable = bool(self.robot.solve_ik(target))
                ik_results.append({"attempt": attempt, "reachable": reachable})
                if reachable:
                    self.robot.attach_fragment(rack.slot)
                    break
        finally:
            self.robot.unlock_base()
        ev = {"rack": rack, "ik_results": ik_results, "inspection": inspection}
        if not ik_results[-1]["reachable"]:
            self.memory.reject_donor(rack.slot, "IK unreachable at the rack")
            return self._go(
                MissionState.COMPUTE_RESTORATION_PLAN, "abstain_harvest", ev, "rejected: IK unreachable at the rack"
            )
        if self.fragment_held is not None and not self.fragment_held():
            self.memory.reject_donor(rack.slot, "grasp did not secure fragment")
            return self._go(MissionState.COMPUTE_RESTORATION_PLAN, "abstain_harvest", ev, "grasp failed")
        identity = getattr(self.robot, "held_fragment_id", None)
        self.fragment_id = identity() if callable(identity) else (rack.fragment_ids[0] if rack.fragment_ids else None)
        if rack.fragment_ids and self.fragment_id not in rack.fragment_ids:
            return self._go(MissionState.ABORTED, "abort", ev, "grasped fragment identity does not match donor inventory")
        self.station.take(rack.genet_id, rack.slot, self.fragment_id)
        self.memory.note_harvest(rack.slot)
        self.carrying = rack.genet_id
        return self._go(MissionState.NAVIGATE_TO_RECIPIENT, "harvest_fragment", {**ev, "stock": self.station.stock()})

    def _recover_fragment(self) -> MissionState:
        """Reacquire the tracked object; inventory must not be decremented again."""
        recover = getattr(self.robot, "recover_lost_fragment", None)
        if not callable(recover) or self.fragment_id is None:
            return self._go(MissionState.ABORTED, "recovery_failed", {}, "persistent fragment identity unavailable")
        result = recover(self.fragment_id, self.recipient_id)
        held = self.fragment_held is not None and bool(self.fragment_held())
        identity = getattr(self.robot, "held_fragment_id", None)
        actual_id = identity() if callable(identity) else result.get("fragment_id")
        same = result.get("fragment_id") == self.fragment_id and actual_id == self.fragment_id
        ev = {"recovery": result, "fragment_held": held, "same_fragment": same, "stock": self.station.stock()}
        if not (result.get("recovered", False) and held and same):
            return self._go(MissionState.ABORTED, "recovery_failed", ev, "same dropped fragment could not be secured")
        self.carrying, self._lost_genet = self._lost_genet, None
        return self._go(MissionState.NAVIGATE_TO_RECIPIENT, "recover_fragment", ev)

    def _navigate_to_recipient(self) -> MissionState:
        if self.returning:
            status, nav_ev = self._navigate(self._station_pose(), carrying=True)
            target = None
        else:
            target = self.registry.get(self.recipient_id)
            if target is None or not is_open_recipient(target) or target.genet_id != self.carrying:
                return self._go(
                    MissionState.COMPUTE_RESTORATION_PLAN,
                    "replan_target_changed",
                    {"recipient_id": self.recipient_id, "recipient_now": entry_summary(target) if target else None},
                    "recipient no longer open for this genet",
                )
            status, nav_ev = self._navigate(self._standoff(target), carrying=True)
        if status == "dislodged":
            self.memory.dislodge_events += 1
            lost = self.carrying
            self._lost_genet = lost
            self.carrying = None
            self.returning = False
            can_recover = callable(getattr(self.robot, "recover_lost_fragment", None))
            return self._go(
                MissionState.RECOVER_FRAGMENT if can_recover else MissionState.COMPUTE_RESTORATION_PLAN,
                "fragment_dislodged",
                {"lost_genet": lost, "recipient_id": self.recipient_id, "navigation": nav_ev},
                "recover the same dropped fragment" if can_recover else "recovery unavailable; re-plan for replacement supply",
            )
        if status != "arrived":
            if target is not None:
                self.memory.note_recipient_attempt(target.cluster_id)
            return self._go(MissionState.COMPUTE_RESTORATION_PLAN, "navigate_failed", {"navigation": nav_ev}, status)
        return self._go(
            MissionState.TRANSPLANT_FRAGMENT,
            "arrive_recipient",
            {
                "recipient": entry_summary(target) if target else None,
                "returning_to_station": self.returning,
                "navigation": nav_ev,
            },
        )

    def _transplant(self) -> MissionState:
        if self.returning:
            self.robot.lock_base()
            try:
                source = self.station.rack_for(self.carrying, self.donor_id)
                self.robot.detach_fragment(Pose(self.station.position_for(source)))
            finally:
                self.robot.unlock_base()
            self.station.put_back(self.carrying, self.donor_id, self.fragment_id)
            self.fragment_id = None
            genet_id, self.carrying, self.returning = self.carrying, None, False
            return self._go(
                MissionState.COMPUTE_RESTORATION_PLAN,
                "fragment_returned_to_station",
                {"genet_id": genet_id, "stock": self.station.stock()},
            )

        target = self.registry.get(self.recipient_id)
        inspection = self._inspect("inspect_recipient", target)
        if inspection is not None and not inspection.get("allowed", False):
            self.memory.reject_recipient(target.cluster_id, "pre-placement inspection rejected")
            return self._go(MissionState.COMPUTE_RESTORATION_PLAN, "abstain_transplant", {"inspection": inspection})
        attempt = self.memory.note_recipient_attempt(target.cluster_id)
        chosen, ev = self._manipulate(target, self.config.graft, self.robot.detach_fragment)
        ev.update(recipient=entry_summary(target), attempt=attempt, fragment_genet=self.carrying,
                  fragment_id=self.fragment_id, inspection=inspection)
        if chosen is None:
            self.memory.reject_recipient(target.cluster_id, ev["failure"])
            return self._go(MissionState.COMPUTE_RESTORATION_PLAN, "abstain_transplant", ev, f"rejected: {ev['failure']}")

        placed_pose = Pose(chosen.position, chosen.orientation_quat)
        self.carrying = None
        if self.placement_verifier is not None:
            verdict = self.placement_verifier(placed_pose)
            ev["placement_verification"] = verdict
            if not (verdict.get("stable", False) and verdict.get("contact", False)):
                if attempt >= self.config.max_attempts_per_recipient:
                    self.memory.reject_recipient(target.cluster_id, f"failed the push test {attempt} times")
                return self._go(
                    MissionState.COMPUTE_RESTORATION_PLAN,
                    "placement_unstable",
                    ev,
                    "fragment shifted or lost contact under push test; colony left open",
                )
        else:
            ev["placement_verification"] = "unverified (no placement_verifier injected)"
            self._unverified.append(target.cluster_id)
        self.registry.upsert(
            dataclasses.replace(
                target,
                health_status="TREATED",
                sampled_or_restored=True,
                optimal_graft_pose_world=chosen.to_graft_pose(),
            )
        )
        outcome = "ok" if self.placement_verifier is not None else "placed, unverified"
        return self._go(MissionState.COMPUTE_RESTORATION_PLAN, "transplant_fragment", ev, outcome)

    # ------------------------------------------------------------- return visits

    def revisit(self, day: int, observe: Callable[[SemanticMapEntry, int], dict]) -> dict[str, str]:
        """Check every treated colony on `day`. Fragments stay in contact throughout."""
        due = [e for e in self.registry.all() if e.health_status == "TREATED"]
        self.state = self._go(
            MissionState.RETURN_VISIT, "revisit_start", {"day": day, "colonies": [e.cluster_id for e in due]}
        )
        final_day = max(self.config.revisit_days)
        results = {}
        for entry in due:
            status, nav_ev = self._navigate(self._standoff(entry), carrying=False)
            if status != "arrived":
                self._go(MissionState.RETURN_VISIT, "navigate_failed", {"navigation": nav_ev, "day": day}, status)
                continue
            observation = observe(entry, day)
            new_status = assess_revisit(day, final_day, observation, self.config.recovered_density_pct)
            self.registry.upsert(dataclasses.replace(entry, health_status=new_status))
            results[entry.cluster_id] = new_status
            self._go(
                MissionState.RETURN_VISIT,
                "revisit_observation",
                {"day": day, "recipient": entry_summary(entry), "observation": observation, "navigation": nav_ev},
                new_status,
            )
        self.state = self._go(MissionState.MISSION_COMPLETE, "revisit_complete", {"day": day, "results": results})
        return results

    # ----------------------------------------------------------------- helpers

    def _inspect(self, name: str, *args) -> Optional[dict]:
        """Optional simulator/robot capability; evidence is never invented by the FSM."""
        hook = getattr(self.robot, name, None)
        if not callable(hook):
            return None
        result = hook(*args)
        if not isinstance(result, dict):
            raise TypeError(f"{name} must return an evidence dict containing allowed")
        return result

    def _station_pose(self) -> Pose:
        source = self.station.rack_for(self.genet_id, self.donor_id)
        navigator = getattr(self.robot, "navigation_pose", None)
        if source is not None and callable(navigator):
            return navigator(source, purpose="donor")
        x, y, z = self.station.position_for(source) if source else self.station.position
        return Pose((x, y, z + self.config.wrist_standoff))

    def _standoff(self, entry: SemanticMapEntry) -> Pose:
        navigator = getattr(self.robot, "navigation_pose", None)
        if callable(navigator):
            return navigator(entry, purpose="recipient")
        x, y, _ = entry.position_world
        return Pose((float(x), float(y), bbox_top(entry) + self.config.wrist_standoff))

    def _navigate(self, target: Pose, carrying: bool) -> tuple[str, dict]:
        """P-controller on position. Returns ("arrived" | "timeout" | "dislodged", evidence)."""
        nav = self.config.nav
        vmax = nav.max_speed * (nav.carry_speed_scale if carrying else 1.0)
        goal = np.asarray(target.position, dtype=float)
        start = self.robot.get_pose().position
        max_ticks = int(np.ceil(nav.timeout_s / nav.dt))
        ticks, status = 0, "arrived"
        while True:
            pos = np.asarray(self.robot.get_pose().position, dtype=float)
            if carrying and self.fragment_held is not None and not self.fragment_held():
                status = "dislodged"
                break
            err = goal - pos
            if np.linalg.norm(err) <= nav.position_tolerance:
                break
            if ticks >= max_ticks:
                status = "timeout"
                break
            v = nav.gain * err
            speed = np.linalg.norm(v)
            if speed > vmax:
                v *= vmax / speed
            self.robot.set_cmd_vel(tuple(float(c) for c in v), (0.0, 0.0, 0.0))
            self.wait(nav.dt)
            self.sim_time += nav.dt
            ticks += 1
        self.robot.set_cmd_vel((0.0, 0.0, 0.0), (0.0, 0.0, 0.0))
        final = self.robot.get_pose().position
        return status, {
            "start": start,
            "target": target.position,
            "final": final,
            "residual_m": distance(final, target.position),
            "path_ticks": ticks,
            "max_speed": vmax,
            "fragment_held": self.fragment_held() if (carrying and self.fragment_held is not None) else None,
        }

    def _manipulate(
        self,
        entry: SemanticMapEntry,
        graft_cfg: GraftConfig,
        act: Callable[[Pose], None],
    ) -> tuple[Optional[GraftCandidate], dict]:
        """lock_base -> wrist RGB-D -> graft candidates -> solve_ik -> act -> unlock_base."""
        cfg = self.config
        observations: list[dict] = []
        ik_results: list[dict] = []
        self.robot.lock_base()
        try:
            contact_selector = getattr(self.robot, "contact_candidate", None)
            if callable(contact_selector):
                candidate, ev = contact_selector(entry)
                ev = dict(ev)
                if candidate is None:
                    ev.setdefault("failure", "no safe natural branch contact candidate")
                    return None, ev
                target = Pose(candidate.position, candidate.orientation_quat)
                reachable = bool(self.robot.solve_ik(target))
                ev.update(ik_results=[{"candidate": 0, "reachable": reachable}], chosen=dataclasses.asdict(candidate))
                if not reachable:
                    ev["failure"] = "IK unreachable at natural branch contact"
                    return None, ev
                act(target)
                return candidate, ev
            result = None
            for _ in range(1 + cfg.reobserve_attempts):
                frame = self.robot.get_wrist_rgbd()
                pose = self.robot.get_pose()
                pts = frame_to_world_points(frame, pose, *cfg.wrist_depth_range)
                on_structure = box_mask(pts, entry, cfg.crop_margin)
                floor = entry.position_world[2] - entry.bounding_box_extent[2] / 2.0 + cfg.crop_margin
                on_structure &= pts[:, 2] > floor
                result = select_graft_candidates(
                    pts[on_structure],
                    obstacles=pts[~on_structure],
                    reach_center=pose.position,
                    config=graft_cfg,
                )
                observations.append({"n_cloud_points": int(len(pts)), **result.evidence})
                if result.candidates:
                    break
            ev: dict = {"observations": observations}
            if not result.candidates:
                ev["failure"] = result.evidence.get("reason", "no graft candidates")
                return None, ev
            ev["candidates"] = [dataclasses.asdict(c) for c in result.candidates]
            for i, c in enumerate(result.candidates):
                target = Pose(c.position, c.orientation_quat)
                reachable = bool(self.robot.solve_ik(target))
                ik_results.append({"candidate": i, "reachable": reachable})
                if reachable:
                    act(target)
                    ev.update(ik_results=ik_results, chosen_candidate=i, chosen=dataclasses.asdict(c))
                    return c, ev
            ev.update(ik_results=ik_results, failure="IK unreachable for all graft candidates")
            return None, ev
        finally:
            self.robot.unlock_base()
