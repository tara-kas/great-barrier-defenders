"""MissionFSM: the on-device mission loop.

    SURVEY_SEABED -> COMPUTE_RESTORATION_PLAN -> NAVIGATE_TO_DONOR ->
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
- `fragment_held() -> bool`: gripper force/camera check for dislodgement.
- `placement_verifier(pose) -> {"stable": bool, ...}`: post-placement push test.
"""

from __future__ import annotations

import dataclasses
import time
from collections import Counter
from dataclasses import dataclass
from enum import Enum
from typing import Any, Callable, Optional

import numpy as np

from agent.config import FSMConfig, GraftConfig
from agent.decision_log import DecisionLog
from agent.evidence import entry_summary, pose_summary, to_jsonable
from agent.geometry import bbox_top, box_mask, distance, frame_to_world_points
from agent.graft_point import GraftCandidate, select_graft_candidates
from agent.memory import EpisodicMemory
from agent.pairing import best_recipient_for_carried, plan_pairs
from agent.robot_interface import Pose, RGBDFrame, RobotInterface
from perception.registry import SemanticMapEntry, SemanticSeabedRegistry

Perceiver = Callable[[RGBDFrame, Pose], list[SemanticMapEntry]]


class MissionState(str, Enum):
    SURVEY_SEABED = "SURVEY_SEABED"
    COMPUTE_RESTORATION_PLAN = "COMPUTE_RESTORATION_PLAN"
    NAVIGATE_TO_DONOR = "NAVIGATE_TO_DONOR"
    HARVEST_FRAGMENT = "HARVEST_FRAGMENT"
    NAVIGATE_TO_RECIPIENT = "NAVIGATE_TO_RECIPIENT"
    TRANSPLANT_FRAGMENT = "TRANSPLANT_FRAGMENT"
    MISSION_COMPLETE = "MISSION_COMPLETE"
    ABORTED = "ABORTED"


TERMINAL = {MissionState.MISSION_COMPLETE, MissionState.ABORTED}


@dataclass
class MissionSummary:
    final_state: str
    steps: int
    sim_time_s: float
    restored: list[str]
    unrestorable: dict[str, str]
    memory: dict[str, Any]


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
        config: FSMConfig = FSMConfig(),
        log: Optional[DecisionLog] = None,
        wait: Callable[[float], None] = time.sleep,
        perceiver: Optional[Perceiver] = None,
        fragment_held: Optional[Callable[[], bool]] = None,
        placement_verifier: Optional[Callable[[Pose], dict]] = None,
    ) -> None:
        self.robot = robot
        self.registry = registry
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
        self.donor_id: Optional[str] = None
        self.recipient_id: Optional[str] = None
        self.carrying: Optional[str] = None  # donor cluster_id of the fragment in the gripper
        self.carried_species: Optional[str] = None
        self.returning = False  # carrying a fragment back to its donor (no recipient left)
        self.unrestorable: dict[str, str] = {}
        self._started = False
        self._survey_queue: Optional[list[tuple[float, float, float]]] = None
        self._handlers: dict[MissionState, Callable[[], MissionState]] = {
            MissionState.SURVEY_SEABED: self._survey,
            MissionState.COMPUTE_RESTORATION_PLAN: self._plan,
            MissionState.NAVIGATE_TO_DONOR: self._navigate_to_donor,
            MissionState.HARVEST_FRAGMENT: self._harvest,
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
        restored = sorted(e.cluster_id for e in self.registry.all() if e.health_status == "RESTORED")
        open_dead = {e.cluster_id for e in self.registry.all() if e.health_status == "DEAD" and not e.sampled_or_restored}
        unrestorable = {}
        for cid in sorted(open_dead):
            reasons = self.memory.recipient_rejections.get(cid)
            unrestorable[cid] = reasons[-1] if reasons else self.unrestorable.get(cid, "not processed")
        return MissionSummary(
            final_state=self.state.value,
            steps=self.steps,
            sim_time_s=round(self.sim_time, 3),
            restored=restored,
            unrestorable=unrestorable,
            memory=self.memory.to_dict(),
        )

    def _go(self, next_state: MissionState, action: str, evidence: dict, outcome: str = "ok") -> MissionState:
        evidence = {
            **evidence,
            "next_state": next_state.value,
            "rov_pose": pose_summary(self.robot.get_pose()),
            "sim_time_s": round(self.sim_time, 3),
            "carrying": self.carrying,
        }
        self.log.record(self.state.value, action, to_jsonable(evidence), outcome)
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
                },
            )
        wp = self._survey_queue.pop(0)
        status, nav_ev = self._navigate(Pose(wp), carrying=False)
        if status != "arrived":
            return self._go(MissionState.SURVEY_SEABED, "survey_waypoint_skipped", {"navigation": nav_ev}, status)
        frame = self.robot.get_hull_rgbd()
        pose = self.robot.get_pose()
        detections = self.perceiver(frame, pose)
        new, updated, kept = [], [], []
        for d in detections:
            result = self._merge_detection(d)
            {"new": new, "updated": updated, "kept": kept}[result].append(d.cluster_id)
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
            },
        )

    def _merge_detection(self, d: SemanticMapEntry) -> str:
        """Upsert a detection without undoing mission progress."""
        existing = self.registry.get(d.cluster_id)
        if existing is None:
            self.registry.upsert(d)
            return "new"
        if existing.health_status == "RESTORED":
            return "kept"
        if existing.sampled_or_restored:
            self.registry.upsert(dataclasses.replace(d, sampled_or_restored=True))
            return "updated"
        self.registry.upsert(d)
        return "updated"

    def _plan(self) -> MissionState:
        cfg = self.config
        rov = self.robot.get_pose().position
        entries = self.registry.all()

        if self.carrying is not None:
            found = best_recipient_for_carried(
                self.carried_species, rov, entries, exclude=self.memory.excluded_recipients()
            )
            if found is None:
                donor = self.registry.get(self.carrying)
                if donor is None:
                    return self._go(
                        MissionState.ABORTED,
                        "abort",
                        {"memory": self.memory.to_dict()},
                        "holding fragment with no recipient and donor unknown; operator needed",
                    )
                self.recipient_id = donor.cluster_id
                self.returning = True
                return self._go(
                    MissionState.NAVIGATE_TO_RECIPIENT,
                    "return_fragment_to_donor",
                    {
                        "species_class": self.carried_species,
                        "reason": "no open recipient of this species left",
                        "donor": entry_summary(donor),
                        "memory": self.memory.to_dict(),
                    },
                )
            recipient, carry_dist = found
            self.recipient_id = recipient.cluster_id
            return self._go(
                MissionState.NAVIGATE_TO_RECIPIENT,
                "select_recipient_for_carried",
                {
                    "species_class": self.carried_species,
                    "recipient": entry_summary(recipient),
                    "carry_distance_m": carry_dist,
                    "memory": self.memory.to_dict(),
                },
            )

        plan = plan_pairs(
            entries,
            rov,
            cfg.weights,
            exclude_donors=self.memory.excluded_donors(),
            exclude_recipients=self.memory.excluded_recipients(),
            min_donor_health=cfg.min_donor_health,
            harvest_counts=self.memory.harvest_counts,
            max_harvests_per_donor=cfg.max_harvests_per_donor,
        )
        for u in plan.unrestorable:
            self.unrestorable[u.recipient_id] = u.reason
        plan_ev = {
            "weights": cfg.weights,
            "n_open_recipients": sum(1 for e in entries if e.health_status == "DEAD" and not e.sampled_or_restored),
            "unrestorable": plan.unrestorable,
            "skipped_donors": plan.skipped_donors,
            "ignored_bleached": plan.ignored_bleached,
            "excluded_recipients": sorted(self.memory.excluded_recipients()),
            "memory": self.memory.to_dict(),
        }
        best = plan.best
        if best is None:
            summary = self.summary()
            return self._go(
                MissionState.MISSION_COMPLETE,
                "mission_complete",
                {**plan_ev, "restored": summary.restored, "unrestorable_final": summary.unrestorable},
            )
        self.donor_id, self.recipient_id = best.donor_id, best.recipient_id
        return self._go(
            MissionState.NAVIGATE_TO_DONOR,
            "select_pair",
            {
                **plan_ev,
                "chosen": best.cost,
                "runners_up_donors": best.runners_up,
                "other_pairings": [p.cost for p in plan.pairings[1:6]],
                "donor": entry_summary(self.registry.get(best.donor_id)),
                "recipient": entry_summary(self.registry.get(best.recipient_id)),
            },
        )

    def _navigate_to_donor(self) -> MissionState:
        donor = self.registry.get(self.donor_id)
        if donor is None or donor.health_status != "LIVE":
            return self._go(
                MissionState.COMPUTE_RESTORATION_PLAN,
                "replan_target_changed",
                {"donor_id": self.donor_id, "donor_now": entry_summary(donor) if donor else None},
                "donor no longer LIVE in registry",
            )
        status, nav_ev = self._navigate(self._standoff(donor), carrying=False)
        if status != "arrived":
            self.memory.reject_donor(donor.cluster_id, f"navigation {status}")
            return self._go(MissionState.COMPUTE_RESTORATION_PLAN, "navigate_failed", {"navigation": nav_ev}, status)
        return self._go(
            MissionState.HARVEST_FRAGMENT, "arrive_donor", {"donor": entry_summary(donor), "navigation": nav_ev}
        )

    def _harvest(self) -> MissionState:
        donor = self.registry.get(self.donor_id)
        if donor is None or donor.health_status != "LIVE":
            return self._go(
                MissionState.COMPUTE_RESTORATION_PLAN,
                "replan_target_changed",
                {"donor_id": self.donor_id},
                "donor no longer LIVE in registry",
            )
        chosen, ev = self._manipulate(donor, self.config.harvest, lambda pose: self.robot.attach_fragment(donor.cluster_id))
        ev["donor"] = entry_summary(donor)
        if chosen is None:
            self.memory.reject_donor(donor.cluster_id, ev["failure"])
            return self._go(MissionState.COMPUTE_RESTORATION_PLAN, "abstain_harvest", ev, f"rejected: {ev['failure']}")
        self.memory.note_harvest(donor.cluster_id)
        self.carrying, self.carried_species = donor.cluster_id, donor.species_class
        self.registry.upsert(dataclasses.replace(donor, sampled_or_restored=True))
        return self._go(MissionState.NAVIGATE_TO_RECIPIENT, "harvest_fragment", ev)

    def _navigate_to_recipient(self) -> MissionState:
        target = self.registry.get(self.recipient_id)
        still_valid = target is not None and (
            self.returning or (target.health_status == "DEAD" and not target.sampled_or_restored)
        )
        if not still_valid:
            return self._go(
                MissionState.COMPUTE_RESTORATION_PLAN,
                "replan_target_changed",
                {"recipient_id": self.recipient_id, "recipient_now": entry_summary(target) if target else None},
                "recipient no longer open in registry",
            )
        status, nav_ev = self._navigate(self._standoff(target), carrying=True)
        if status == "dislodged":
            self.memory.dislodge_events += 1
            lost = self.carrying
            self.carrying = self.carried_species = None
            self.returning = False
            return self._go(
                MissionState.COMPUTE_RESTORATION_PLAN,
                "fragment_dislodged",
                {"lost_fragment_from": lost, "recipient_id": self.recipient_id, "navigation": nav_ev},
                "fragment lost mid-carry; re-planning to re-acquire",
            )
        if status != "arrived":
            self.memory.note_recipient_attempt(target.cluster_id)
            return self._go(MissionState.COMPUTE_RESTORATION_PLAN, "navigate_failed", {"navigation": nav_ev}, status)
        return self._go(
            MissionState.TRANSPLANT_FRAGMENT,
            "arrive_recipient",
            {"recipient": entry_summary(target), "returning_to_donor": self.returning, "navigation": nav_ev},
        )

    def _transplant(self) -> MissionState:
        target = self.registry.get(self.recipient_id)
        if self.returning:
            chosen, ev = self._manipulate(target, self.config.harvest, self.robot.detach_fragment)
            if chosen is None:
                return self._go(
                    MissionState.ABORTED, "abort", ev, f"could not return fragment to donor: {ev['failure']}; operator needed"
                )
            self.carrying = self.carried_species = None
            self.returning = False
            return self._go(MissionState.COMPUTE_RESTORATION_PLAN, "fragment_returned_to_donor", ev)

        attempt = self.memory.note_recipient_attempt(target.cluster_id)
        chosen, ev = self._manipulate(target, self.config.graft, self.robot.detach_fragment)
        ev.update(recipient=entry_summary(target), attempt=attempt, fragment_from=self.carrying)
        if chosen is None:
            self.memory.reject_recipient(target.cluster_id, ev["failure"])
            return self._go(MissionState.COMPUTE_RESTORATION_PLAN, "abstain_transplant", ev, f"rejected: {ev['failure']}")

        placed_pose = Pose(chosen.position, chosen.orientation_quat)
        self.carrying = self.carried_species = None
        if self.placement_verifier is not None:
            verdict = self.placement_verifier(placed_pose)
            ev["placement_verification"] = verdict
            if not verdict.get("stable", False):
                return self._go(
                    MissionState.COMPUTE_RESTORATION_PLAN,
                    "placement_unstable",
                    ev,
                    "fragment shifted under push test; recipient left open",
                )
        else:
            ev["placement_verification"] = "unverified (no placement_verifier injected)"
        self.registry.upsert(
            dataclasses.replace(
                target,
                health_status="RESTORED",
                sampled_or_restored=True,
                optimal_graft_pose_world=chosen.to_graft_pose(),
            )
        )
        return self._go(MissionState.COMPUTE_RESTORATION_PLAN, "transplant_fragment", ev)

    # ----------------------------------------------------------------- helpers

    def _standoff(self, entry: SemanticMapEntry) -> Pose:
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
