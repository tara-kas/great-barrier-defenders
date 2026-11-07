"""Deterministic reef mission and reduced underwater dynamics, without GPU dependencies.

World coordinates are metres, Z-up. Truth lives in ``corals``; mission planning
reads only ``observations``. This is a synthetic observation model, not a learned
coral classifier. The Isaac adapter renders the same authoritative mission state.
"""
from __future__ import annotations

import copy
import heapq
import math
import random

from .config import load_config


def distance(a, b):
    return math.sqrt(sum((x - y) ** 2 for x, y in zip(a, b)))


def clamp(value, low, high):
    return max(low, min(high, value))


class ReefSimulation:
    def __init__(self, config=None):
        self.config = load_config(config)
        self._reset()

    def _reset(self):
        self.rng = random.Random(self.config["seed"])
        self.time = 0.0
        self.paused = False
        self.water = copy.deepcopy(self.config["water"])
        self.regions = copy.deepcopy(self.config["regions"])
        self.observations = {}
        self.events = []
        self._detection_history = []
        self.collisions = 0
        self.duplicate_assignments = 0
        self._sensor_clock = 0.0
        self._trail_clock = 0.0
        self._complete_announced = False
        self.obstacles = [
            {"id": "rock-01", "position": [-0.6, -0.1, 0.0], "radius": 0.65, "height": 1.15},
            {"id": "rock-02", "position": [0.9, 0.65, 0.0], "radius": 0.5, "height": 0.9},
            {"id": "rubble", "position": [-2.6, 2.45, 0.0], "radius": 1.05, "height": 0.6},
        ]
        self.corals = self._generate_corals()
        self._prepare_contact_corals()
        self._assign_planting_points()
        self._truth_by_id = {coral["id"]: coral for coral in self.corals}
        self.fragments = self._generate_fragments()
        self._fragments_by_id = {fragment["id"]: fragment for fragment in self.fragments}
        self.robots = [self._robot("scout-01", "survey", [-4.3, -4.1, 1.65]),
                       self._robot("restore-02", "restoration", [-3.65, -3.65, 1.35])]
        # The minimum supported 8 m world needs in-bounds launch positions;
        # clamping an outside launch can otherwise trigger separation guards.
        for robot in self.robots:
            robot["position"][0] *= min(1., self.config["world"]["width"] / 10)
            robot["position"][1] *= min(1., self.config["world"]["length"] / 10)
            robot["trail"] = [robot["position"][:]]
        self._survey_waypoints = self._survey_path()
        self._survey_index = 0
        for robot in self.robots:
            robot["gripper_world"] = self._stowed_gripper(robot)
        self._event("mission", "Mission initialized · healthy donor fragments assist bleached but living coral")

    @property
    def _contact_mode(self):
        return self.config["mission"]["attachment_method"] == "same_genet_contact"

    @property
    def _detection_required(self):
        return bool(self.config["inspection"].get("require_detection"))

    def _prepare_contact_corals(self):
        """Known clonal lineages are scenario metadata, never colour inference.

        The optional contact experiment uses a Pocillopora-inspired visual
        proxy and enlarged cuttings. Baseline limestone missions retain their
        existing species, shape, geometry, donor distribution and trajectory.
        """
        if not self._contact_mode:
            return
        donors = [c for c in self.corals if c["donor_capacity"] > 0]
        recipients = [c for c in self.corals if c["substrate_suitable"]]
        assignments = {c["id"]: ("R" if i % 2 == 0 else "G")
                       for i, c in enumerate(donors)}
        assignments.update({c["id"]: ("R" if i % 2 == 0 else "G")
                            for i, c in enumerate(recipients)})
        assignments.update(self.config["mission"]["genet_assignments"])
        for coral in self.corals:
            participating = coral in donors or coral in recipients
            genet = assignments.get(coral["id"])
            coral.update(attachment_method="same_genet_contact", genet_id=genet,
                         genotype_known=bool(genet), genotype_source="synthetic_clonal_lineage_registry",
                         genet_marker={"R": "red", "G": "green"}.get(genet),
                         fluorescence_marker={"R": "red", "G": "green"}.get(genet),
                         contact_base=None, contact_point=None, contact_normal=None, contact_fixture=None)
            if participating:
                coral["morphology"] = "branching"
                coral["species"] = "pocillopora_damicornis_proxy"
                coral["height"] = min(coral["height"], coral["radius"])

    def _robot(self, robot_id, role, position):
        return {"id": robot_id, "role": role, "position": position[:],
                "velocity": [0.0, 0.0, 0.0], "yaw": 0.0,
                "state": "SURVEY" if role == "survey" else "WAIT_FOR_MAP",
                "target": None, "carrying": False, "available": True,
                "trail": [position[:]], "distance_travelled": 0.0,
                "arm_extension": 0.0, "task_id": None, "dwell": 0.0,
                "gripper_world": None, "gripper_open": 1.0, "donor_id": None, "fragment_id": None,
                "manipulation_phase": "idle", "phase_progress": 0.0,
                "_phase_start": None, "_phase_end": None,
                "_path": [], "_path_goal": None, "_trail_clock": 0.0}

    def _generate_corals(self):
        corals = []
        offsets = [(-0.9, -0.5), (0.0, -0.9), (0.9, -0.3),
                   (-0.65, 0.55), (0.3, 0.8), (1.05, 0.65)]
        for region in self.regions:
            for index, (ox, oy) in enumerate(offsets):
                cx, cy, _ = region["center"]
                x, y = cx + ox + self.rng.uniform(-0.15, 0.15), cy + oy + self.rng.uniform(-0.15, 0.15)
                morphology = "branching" if index % 2 == 0 else "boulder"
                eligible = (region["health"] == "bleached_alive" and region["policy"] == "plant"
                            and index < self.config["mission"]["planting_sites"])
                height = self.rng.uniform(0.40, 0.78)
                radius = self.rng.uniform(0.23, 0.40)
                if morphology == "boulder":
                    # Massive coral grows as a low dome, not a tall rock.
                    # The same height drives sensor truth and attachment poses.
                    radius *= 1.15
                    height = radius * (.80 + .25 * (height - .40) / .38)
                # Keep the colony surface outside solid outcrops. Low domes
                # otherwise disappear inside the rubble mesh and cannot be
                # observed from any direction.
                for obstacle in self.obstacles:
                    dx, dy = x - obstacle["position"][0], y - obstacle["position"][1]
                    d = math.hypot(dx, dy)
                    clearance = obstacle["radius"] + radius * .70 + .04
                    if d < clearance:
                        direction = math.atan2(dy, dx) if d > 1e-6 else index * math.pi / 3
                        x = obstacle["position"][0] + math.cos(direction) * clearance
                        y = obstacle["position"][1] + math.sin(direction) * clearance
                corals.append({
                    "id": f"coral-{len(corals) + 1:03d}", "position": [x, y, 0.0],
                    "height": height, "radius": radius,
                    "morphology": morphology, "species": "acropora_sp" if morphology == "branching" else "porites_sp",
                    "health": region["health"], "region_id": region["id"],
                    "substrate_suitable": eligible, "observed": False,
                    "task_status": "unobserved", "fragment_attached": False,
                    "reserved_by": None, "attachment_position": None,
                    "fragment_index": None, "fragment_id": None, "source_donor_id": None,
                    "planting_point": None,
                    "donor_capacity": self.config["donors"]["fragments_per_colony"] if region["health"] == "healthy" and morphology == "branching" else 0,
                    "harvested_fragments": 0,
                    "_measurement_error": [self.rng.uniform(-0.025, 0.025) for _ in range(2)]
                })
        return corals

    def _assign_planting_points(self):
        """Reserve unobstructed mounts after every semantic colony is known.

        The whole wrist/camera workspace, not just the cutting's base, must
        clear neighbouring colonies. This deterministic search consumes no
        random draws, so changing mount layout never changes reef geometry.
        A layout without a safe mount is rejected rather than rendered with a
        tool or cutting embedded in another colony.
        """
        if self._contact_mode:
            self._assign_contact_points()
            return
        workspace = .55
        half_width = self.config["world"]["width"] / 2 - .50
        half_length = self.config["world"]["length"] / 2 - .50
        occupied = self.corals + self.obstacles
        mounts = []
        for coral in self.corals:
            if not coral["substrate_suitable"]:
                continue
            region = next(r for r in self.regions if r["id"] == coral["region_id"])
            candidates = []
            for ring in range(40):
                radius = coral["radius"] + workspace + .06 * ring
                for sector in range(96):
                    angle = -math.pi / 8 + sector * math.tau / 96
                    x = coral["position"][0] + radius * math.cos(angle)
                    y = coral["position"][1] + radius * math.sin(angle)
                    if abs(x) > half_width or abs(y) > half_length:
                        continue
                    if math.hypot(x - region["center"][0], y - region["center"][1]) > region["radius"] - .12:
                        continue
                    if any(math.hypot(x - item["position"][0], y - item["position"][1]) < item["radius"] + workspace
                           for item in occupied):
                        continue
                    if any(math.hypot(x - mount[0], y - mount[1]) < .70 for mount in mounts):
                        continue
                    # Prefer a nearby mounting surface, with a small fixed
                    # east/south preference to make ties reproducible.
                    score = radius + .04 * (1 - math.cos(angle + .3))
                    candidates.append((score, x, y))
            if not candidates:
                raise ValueError(f"No clear bleached-coral assistance workspace for {coral['id']}")
            _, x, y = min(candidates)
            coral["planting_point"] = [x, y, .075]
            mounts.append(coral["planting_point"])

    def _assign_contact_points(self):
        """Choose a real, accessible surface on each existing recipient mesh.

        The small basal support is separate from living tissue. No extension
        branch is generated to reach an arbitrary point in open water.
        """
        from .natural_contact import natural_contact_candidates
        half_width = self.config["world"]["width"] / 2 - .50
        half_length = self.config["world"]["length"] / 2 - .50
        contacts = []
        mesh_detail = "hero" if self.config.get("render", {}).get("realistic_tissue", False) else "standard"
        for index, coral in enumerate(self.corals):
            if not coral["substrate_suitable"]:
                continue
            blockers = [c for c in self.corals if c is not coral] + self.obstacles
            candidates = []
            mesh_seed = int(self.config["seed"]) + index * 813
            for candidate in natural_contact_candidates(coral, mesh_seed, detail=mesh_detail):
                base, normal = candidate["base"], candidate["normal"]
                x, y = base[:2]
                if abs(x) > half_width or abs(y) > half_length:
                    continue
                clearance = min(math.hypot(x-c["position"][0],y-c["position"][1])-c["radius"] for c in blockers)
                if clearance < .55:
                    continue
                if any(math.hypot(x-p[0],y-p[1]) < .70 for p in contacts):
                    continue
                dx, dy = x-coral["position"][0], y-coral["position"][1]
                outward = dx*normal[0] + dy*normal[1]
                hull_clearance = coral["radius"] + self.config["robot"]["radius"] + .04
                offset = max(.32, -outward + math.sqrt(max(0., outward*outward + hull_clearance*hull_clearance - dx*dx - dy*dy)))
                body_x, body_y = x+offset*normal[0], y+offset*normal[1]
                if abs(body_x)>half_width or abs(body_y)>half_length:
                    continue
                if any(math.hypot(body_x-c["position"][0],body_y-c["position"][1]) < c["radius"]+.34 for c in blockers):
                    continue
                score = candidate["score"] + .12*clearance - .10*offset
                candidates.append((score,candidate,offset,clearance))
            if not candidates:
                raise ValueError(f"No accessible natural recipient branch for {coral['id']}")
            _, chosen, offset, clearance = max(candidates,key=lambda item:item[0])
            base, point, normal = chosen["base"], chosen["point"], chosen["normal"]
            fixture = {"kind": "natural_branch", "recipient_id": coral["id"],
                       "recipient_mesh": "Colony", "source_mesh_seed": mesh_seed,
                       "source_mesh_detail": mesh_detail,
                       "source_vertex_count": chosen["source_vertex_count"],
                       "source_triangle_count": chosen["source_triangle_count"],
                       "source_triangle_index": chosen["triangle_index"],
                       "contact_triangle_world": chosen["triangle"],
                       "contact_patch_triangle_indices": chosen["patch_triangles"],
                       "support_point": chosen["support_point"],
                       "donor_contact_radius": .0048, "contact_z_offset": .020,
                       "contact_band_local_z": [.010,.035], "contact_tolerance_m": .0015,
                       "contact_patch_radius_m": .025, "body_outward_offset_m": offset,
                       "other_workspace_clearance_m": .55,
                       "measured_other_clearance_m": clearance,
                       "support": "small basal adhesive saddle against existing natural branch, below living contact",
                       "contact_exception": "existing recipient branch contact patch only"}
            coral.update(planting_point=base[:],contact_base=base[:],contact_point=point,
                         contact_normal=normal,contact_fixture=fixture)
            contacts.append(base)

    def _generate_fragments(self):
        """Small persistent branch tips present on living donors from reset.

        A fragment is one object for its entire lifecycle. Renderers must move
        this object rather than generate a new colony/roots after placement.
        """
        fragments = []
        limit = self.config["donors"]["max_fragments"]
        for coral in self.corals:
            for slot in range(coral["donor_capacity"]):
                if len(fragments) >= limit:
                    return fragments
                angle = (-.65 if slot == 0 else .65)
                radial = coral["radius"] * .78
                position = [coral["position"][0] + math.cos(angle) * radial,
                            coral["position"][1] + math.sin(angle) * radial,
                            coral["height"] * (.72 if slot == 0 else .82)]
                index = len(fragments)
                fragments.append({"id": f"fragment-{index + 1:03d}", "index": index,
                    "donor_id": coral["id"], "seed": 730 + index, "radius": .025,
                    "height": .14, "position": position[:], "base_world": position[:],
                    "source_position": position[:], "yaw": angle, "stage": "attached_to_donor",
                    "source_species": coral["species"], "target_id": None,
                    "reserved_by": None})
                if self._contact_mode:
                    fragments[-1].update(genet_id=coral["genet_id"], genotype_known=coral["genotype_known"],
                                         genotype_source=coral["genotype_source"], genet_marker=coral["genet_marker"],
                                         fluorescence_marker=coral["fluorescence_marker"],
                                         attachment_method="same_genet_contact")
        return fragments

    def _stowed_gripper(self, robot):
        yaw = robot["yaw"]
        return [robot["position"][0] + .34 * math.cos(yaw),
                robot["position"][1] + .34 * math.sin(yaw), robot["position"][2] - .32]

    @staticmethod
    def _smooth(a, b, progress):
        t = clamp(progress, 0., 1.)
        t = t * t * (3. - 2. * t)
        return [a[i] * (1. - t) + b[i] * t for i in range(3)]

    def _enter_phase(self, robot, state, end=None):
        robot["state"] = state
        robot["manipulation_phase"] = state.lower()
        robot["dwell"] = 0.
        robot["phase_progress"] = 0.
        robot["_phase_start"] = robot["gripper_world"][:]
        robot["_phase_end"] = end[:] if end is not None else robot["gripper_world"][:]

    def _phase_tick(self, robot, dt, key):
        if self._settled(robot):
            robot["dwell"] += dt
        duration = self.config["mission"][key]
        robot["phase_progress"] = clamp(robot["dwell"] / duration, 0., 1.)
        return robot["phase_progress"] >= 1. - 1e-9

    def _sync_attachments(self):
        for robot in self.robots:
            if not robot["available"]:
                continue
            if robot["state"] in ("SURVEY", "SURVEY_COMPLETE", "WAIT_FOR_MAP", "PLAN", "COMPLETE",
                                   "NO_STOCK", "NO_COMPATIBLE_DONOR", "NAVIGATE_TO_DONOR", "NAVIGATE_TO_SITE",
                                   "NAVIGATE_TO_SCAN_RECIPIENT", "SCAN_RECIPIENT", "SCAN_DONOR", "NAVIGATE_TO_PICKUP"):
                robot["gripper_world"] = self._stowed_gripper(robot)
                robot["gripper_open"] = 0. if robot["carrying"] else 1.
            fragment = self._fragments_by_id.get(robot.get("fragment_id"))
            if fragment is not None and fragment["stage"] == "carried":
                fragment["position"] = [*robot["gripper_world"][:2], robot["gripper_world"][2] - .045]
                fragment["base_world"] = fragment["position"][:]
                fragment["yaw"] = robot["yaw"] + fragment.get("_grasp_yaw_offset", 0.)

    def _survey_path(self):
        points = []
        half_width = min(4.1, self.config["world"]["width"] / 2 - .50)
        half_length = min(4.1, self.config["world"]["length"] / 2 - .50)
        # Closely spaced lanes keep the camera useful in moderately turbid water.
        for index in range(7):
            y = -half_length + index * (2 * half_length / 6)
            xs = [-half_width, half_width] if index % 2 == 0 else [half_width, -half_width]
            points.extend([[x, y, self.config["robot"]["survey_altitude"]] for x in xs])
        # Low massive colonies can be hidden behind the rubble outcrop from
        # the main transects. Inspect its west side from a safe second angle.
        points.append([-half_width, min(2.8, half_length), self.config["robot"]["survey_altitude"]])
        return points

    def _event(self, event_type, message, **fields):
        self.events.append({"time": round(self.time, 2), "type": event_type, "message": message, **fields})
        self.events = self.events[-80:]

    def command(self, command):
        """Apply a control command. Invalid values are rejected without mutation."""
        action = command.get("action", command.get("command", command.get("type", "")))
        if action == "pause":
            self.paused = True
        elif action in ("resume", "play", "start"):
            self.paused = False
        elif action == "reset":
            if "seed" in command:
                self.config["seed"] = int(command["seed"])
            self._reset()
        elif action in ("set_water", "water"):
            updates = {key: command[key] for key in ("visibility", "current", "turbidity") if key in command}
            if isinstance(command.get("water"), dict):
                updates.update(command["water"])
            allowed = {key: value for key, value in updates.items() if key in ("visibility", "current", "turbidity")}
            merged = load_config({"water": {**self.water, **allowed}})
            self.water = merged["water"]
            self._event("environment", f"Water updated · visibility {self.water['visibility']:.1f} m")
        elif action in ("set_robot_available", "robot"):
            robot_id = command.get("robot_id", command.get("id"))
            robot = next((r for r in self.robots if r["id"] == robot_id), None)
            if robot is None:
                raise ValueError("Unknown robot_id")
            robot["available"] = bool(command.get("available", True))
            self._event("fleet", f"{robot_id} {'online' if robot['available'] else 'holding'}")
        else:
            raise ValueError(f"Unknown action: {action}")
        return {"ok": True, "action": action, "paused": self.paused}

    def step(self, dt):
        if not math.isfinite(dt) or dt < 0:
            raise ValueError("dt must be finite and non-negative")
        if self.paused:
            return
        # Bounded substeps keep drag integration stable regardless of viewer rate.
        remaining = dt
        while remaining > 1e-9:
            h = min(remaining, 0.05)
            self.time += h
            self._update_mission(h)
            for robot in self.robots:
                self._integrate(robot, h)
            self._sync_attachments()
            self._sensor_clock += h
            if self._sensor_clock >= self.config["robot"]["camera_period"] - 1e-9:
                self._sensor_clock = 0.0
                self._observe()
            remaining -= h

    def _update_mission(self, dt):
        scout, worker = self.robots
        if scout["available"]:
            if self._survey_index < len(self._survey_waypoints):
                scout["state"] = "SURVEY"
                waypoint = self._survey_waypoints[self._survey_index][:]
                waypoint[2] = max(1.1, min(self.config["robot"]["survey_altitude"], self.water["visibility"] * 0.56))
                scout["target"] = waypoint
                if distance(scout["position"], waypoint) < 0.22:
                    self._survey_index += 1
                    if self._survey_index == len(self._survey_waypoints):
                        self._event("survey", "Survey complete · holding for verification")
            else:
                scout["state"] = "SURVEY_COMPLETE"
        if not worker["available"]:
            return
        state = worker["state"]
        if state == "DETECTION_REJECTED":
            return
        if state in ("WAIT_FOR_MAP", "PLAN", "COMPLETE", "NO_STOCK", "NO_COMPATIBLE_DONOR"):
            targets = [obs for obs in self.observations.values()
                       if obs["task_status"] == "eligible" and obs["health"] == "bleached_alive"
                       and obs["confidence"] >= .45]
            donors = {obs["id"] for obs in self.observations.values()
                      if obs["health"] == "healthy" and obs.get("morphology") == "branching"
                      and (not self._contact_mode or (obs.get("genotype_known") and obs.get("genet_id")))}
            fragments = [fragment for fragment in self.fragments
                         if fragment["donor_id"] in donors and fragment["stage"] == "attached_to_donor"
                         and fragment["reserved_by"] is None]
            pairs = [(target, fragment) for target in targets for fragment in fragments
                     if not self._contact_mode or (target.get("genotype_known") and fragment.get("genotype_known")
                         and target.get("genet_id") == fragment.get("genet_id")
                         and self.observations[fragment["donor_id"]].get("genet_id") == fragment.get("genet_id")
                         and target.get("species") == fragment.get("source_species")
                         and self.observations[fragment["donor_id"]].get("species") == fragment.get("source_species"))]
            if pairs:
                target, fragment = min(pairs, key=lambda pair:
                    distance(worker["position"], pair[1]["position"]) +
                    1.2 * distance(pair[1]["position"], pair[0]["position"]))
                truth = self._truth_by_id[target["id"]]
                if truth["reserved_by"] is not None:
                    self.duplicate_assignments += 1
                    return
                target.update(task_status="reserved", reserved_by=worker["id"])
                truth.update(task_status="reserved", reserved_by=worker["id"])
                fragment.update(reserved_by=worker["id"], target_id=target["id"])
                worker.update(task_id=target["id"], donor_id=fragment["donor_id"],
                              fragment_id=fragment["id"], fragment_index=fragment["index"],
                              state="NAVIGATE_TO_DONOR", manipulation_phase="transit_to_donor")
                source = fragment["source_position"]
                worker["target"] = [source[0], source[1], max(.90, source[2] + .045 + .55)]
                if self._detection_required:
                    fragment["detection_evidence"] = {}
                    fragment.pop("detection_approved_at", None)
                    worker["detection_status"] = "pending_recipient"
                    self._begin_scan_navigation(worker, truth, "recipient")
                self._event("assignment", f"Living donor {fragment['donor_id']} → bleached living coral {target['id']}",
                            coral_id=target["id"], donor_id=fragment["donor_id"], fragment_id=fragment["id"],
                            **({"genet_id": fragment["genet_id"], "attachment_method": "same_genet_contact"}
                               if self._contact_mode else {}))
            elif targets and self._contact_mode and self._survey_index >= len(self._survey_waypoints):
                worker["state"] = "NO_COMPATIBLE_DONOR"
            elif targets and not any(f["stage"] == "attached_to_donor" for f in self.fragments):
                worker["state"] = "NO_STOCK"
            elif not targets and self._survey_index >= len(self._survey_waypoints):
                worker["state"] = "COMPLETE"
                if not self._complete_announced:
                    self._event("mission", "Contact grafts secured · same-genet tissue contact verified; biological recovery pending"
                                if self._contact_mode else "Assistance complete · donor fragments released beside bleached living colonies; health unchanged")
                    self._complete_announced = True
            else:
                worker["state"] = "WAIT_FOR_MAP"
            return

        fragment = self._fragments_by_id[worker["fragment_id"]]
        source_grasp = [*fragment["source_position"][:2], fragment["source_position"][2] + .045]
        target_coral = self._truth_by_id[worker["task_id"]]
        observation = self.observations[worker["task_id"]]
        mounting_base = observation.get("planting_point") or target_coral["planting_point"]
        mounting_grasp = [*mounting_base[:2], mounting_base[2] + .045]
        if self._detection_required:
            if state in ("NAVIGATE_TO_SCAN_RECIPIENT", "NAVIGATE_TO_DONOR", "SCAN_RECIPIENT", "SCAN_DONOR"):
                self._update_detection(worker, fragment, dt)
                return
            if state in ("NAVIGATE_TO_PICKUP", "APPROACH_FRAGMENT", "CLOSE_GRIPPER", "DETACH_FRAGMENT",
                         "RETRACT_FRAGMENT", "NAVIGATE_TO_SITE", "LOWER_FRAGMENT", "SECURE_FRAGMENT", "OPEN_GRIPPER"):
                if not self._pair_detection_approved(worker, fragment):
                    self._reject_detection(worker, fragment, "approval_invalidated")
                    return
        if state in ("NAVIGATE_TO_DONOR", "NAVIGATE_TO_PICKUP"):
            if self._settled(worker):
                self._enter_phase(worker, "APPROACH_FRAGMENT", source_grasp)
                self._event("approach", "Opening jaws around a live donor branch tip", fragment_id=fragment["id"])
        elif state == "APPROACH_FRAGMENT":
            done = self._phase_tick(worker, dt, "approach_duration")
            worker["arm_extension"] = worker["phase_progress"]
            worker["gripper_open"] = 1.
            worker["gripper_world"] = self._smooth(worker["_phase_start"], worker["_phase_end"], worker["phase_progress"])
            if done:
                self._enter_phase(worker, "CLOSE_GRIPPER")
        elif state == "CLOSE_GRIPPER":
            done = self._phase_tick(worker, dt, "close_duration")
            worker["gripper_open"] = 1. - worker["phase_progress"]
            if done:
                fragment["stage"] = "grasped"
                self._enter_phase(worker, "DETACH_FRAGMENT")
                self._event("grasp", "Jaws closed on the stem · fragment remains at donor until detachment", fragment_id=fragment["id"])
        elif state == "DETACH_FRAGMENT":
            done = self._phase_tick(worker, dt, "detach_duration")
            worker["gripper_open"] = 0.
            if done:
                fragment["_grasp_yaw_offset"] = fragment["yaw"] - worker["yaw"]
                fragment["stage"] = "carried"
                if self._detection_required:
                    fragment["harvested_at"] = self.time
                worker["carrying"] = True
                self._truth_by_id[fragment["donor_id"]]["harvested_fragments"] += 1
                self._enter_phase(worker, "RETRACT_FRAGMENT", self._stowed_gripper(worker))
                self._event("detach", "Branch tip detached · the same fragment retracts with the closed gripper", fragment_id=fragment["id"])
        elif state == "RETRACT_FRAGMENT":
            done = self._phase_tick(worker, dt, "retract_duration")
            worker["gripper_world"] = self._smooth(worker["_phase_start"], worker["_phase_end"], worker["phase_progress"])
            worker["arm_extension"] = 1. - worker["phase_progress"]
            if done:
                worker.update(state="NAVIGATE_TO_SITE", manipulation_phase="carrying")
                worker["target"] = [mounting_base[0], mounting_base[1], max(.90, mounting_base[2] + .55)]
                if self._contact_mode:
                    normal = target_coral["contact_normal"]
                    offset = target_coral["contact_fixture"]["body_outward_offset_m"]
                    worker["target"][0] += offset * normal[0]
                    worker["target"][1] += offset * normal[1]
        elif state == "NAVIGATE_TO_SITE":
            aligned = True
            if self._contact_mode:
                normal = target_coral["contact_normal"]
                desired_yaw = math.atan2(-normal[1], -normal[0])
                aligned = abs((desired_yaw - worker["yaw"] + math.pi) % math.tau - math.pi) < .04
            if self._settled(worker) and aligned:
                self._enter_phase(worker, "LOWER_FRAGMENT", mounting_grasp)
                self._event("placement", "Aligning same-genet living tissue at recipient contact branch"
                            if self._contact_mode else "Assisting bleached living coral · lowering the fragment onto a nearby stable mount", fragment_id=fragment["id"])
        elif state == "LOWER_FRAGMENT":
            done = self._phase_tick(worker, dt, "lower_duration")
            worker["gripper_world"] = self._smooth(worker["_phase_start"], worker["_phase_end"], worker["phase_progress"])
            worker["arm_extension"] = worker["phase_progress"]
            worker["gripper_open"] = 0.
            if done:
                self._enter_phase(worker, "SECURE_FRAGMENT")
        elif state == "SECURE_FRAGMENT":
            done = self._phase_tick(worker, dt, "secure_duration")
            worker["gripper_open"] = 0.
            if done:
                self._enter_phase(worker, "OPEN_GRIPPER")
                self._event("release", "Contact fixture secured · opening the gripper while tissue faces remain touching"
                            if self._contact_mode else "Attachment seated · opening the gripper before withdrawal", fragment_id=fragment["id"])
        elif state == "OPEN_GRIPPER":
            done = self._phase_tick(worker, dt, "open_duration")
            worker["gripper_open"] = worker["phase_progress"]
            if done:
                fragment.update(stage="placed", position=mounting_base[:], base_world=mounting_base[:])
                worker["carrying"] = False
                target_coral.update(fragment_attached=True, fragment_index=fragment["index"],
                                    fragment_id=fragment["id"], source_donor_id=fragment["donor_id"],
                                    attachment_position=mounting_base[:], task_status="fragment_attached")
                if self._contact_mode:
                    target_coral.update(graft_contact_secured=True, graft_secured_at=self.time,
                                        biological_recovery="pending_not_simulated")
                observation["task_status"] = "fragment_attached"
                self._enter_phase(worker, "RETRACT_GRIPPER", self._stowed_gripper(worker))
                self._event("attachment", "Same fragment released in recipient tissue contact · biological fusion pending"
                            if self._contact_mode else "Fragment released at the mount · no growth or roots generated", fragment_id=fragment["id"])
        elif state == "RETRACT_GRIPPER":
            done = self._phase_tick(worker, dt, "retreat_duration")
            worker["gripper_world"] = self._smooth(worker["_phase_start"], worker["_phase_end"], worker["phase_progress"])
            worker["arm_extension"] = 1. - worker["phase_progress"]
            worker["gripper_open"] = 1.
            if done:
                self._enter_phase(worker, "VERIFY_ATTACHMENT")
        elif state == "VERIFY_ATTACHMENT":
            done = self._phase_tick(worker, dt, "verification_dwell")
            if done:
                target_coral["task_status"] = "verified"
                observation["task_status"] = "verified"
                self._event("verification", f"{'Mechanical contact' if self._contact_mode else 'Engineering assistance'} verified · {fragment['id']} at {target_coral['id']}", fragment_id=fragment["id"])
                worker.update(task_id=None, donor_id=None, fragment_id=None, state="PLAN",
                              arm_extension=0., manipulation_phase="idle", phase_progress=0.)

    def _begin_scan_navigation(self, worker, coral, role):
        from .uv_detection import scan_plan
        plan = scan_plan(coral, self.config)
        worker.update(state="NAVIGATE_TO_SCAN_RECIPIENT" if role == "recipient" else "NAVIGATE_TO_DONOR",
                      target=plan["body_target"], scan_target_id=coral["id"],
                      scan_target_world=plan["target_world"], scan_role=role,
                      scan_standoff_m=plan["standoff_m"], scan_coverage_radius_m=plan["coverage_radius_m"],
                      _scan_yaw=plan["yaw"], manipulation_phase="transit_to_scan_"+role,
                      dwell=0., phase_progress=0., gripper_open=1.)

    @staticmethod
    def _clear_scan(worker):
        for key in ("scan_target_id", "scan_target_world", "scan_role", "scan_standoff_m",
                    "scan_coverage_radius_m", "_scan_yaw"):
            worker[key] = None

    def _update_detection(self, worker, fragment, dt):
        from .uv_detection import evaluate_detection, mission_profile
        role = worker["scan_role"]
        aligned = abs((worker["_scan_yaw"]-worker["yaw"]+math.pi) % math.tau-math.pi) < .04
        settled = self._settled(worker) and aligned
        state = "SCAN_"+role.upper()
        if worker["state"] != state:
            if settled:
                self._enter_phase(worker, state)
            return
        if settled:
            worker["dwell"] += dt
        else:
            # A scan requires one uninterrupted stationary exposure interval.
            worker["dwell"] = 0.
        worker["phase_progress"] = min(1., worker["dwell"]/self.config["inspection"]["detection_duration"])
        if worker["phase_progress"] < 1.-1e-9:
            return
        coral = self._truth_by_id[worker["scan_target_id"]]
        paired_id = worker["donor_id"] if role == "recipient" else worker["task_id"]
        paired = self._truth_by_id[paired_id]
        receipt = evaluate_detection(coral, paired, worker, self.config, role=role, timestamp=self.time,
                                     observed=self.observations.get(coral["id"]),
                                     counterpart_observed=self.observations.get(paired_id),
                                     blockers=self.corals+self.obstacles, fragment=fragment,
                                     profile=mission_profile(coral, self.corals.index(coral), self.config["seed"]))
        self._detection_history.append(copy.deepcopy(receipt))
        coral.setdefault("detection_history", []).append(copy.deepcopy(receipt))
        coral["uv_detection"] = copy.deepcopy(receipt)
        worker["uv_detection"] = copy.deepcopy(receipt)
        fragment["detection_evidence"][role] = copy.deepcopy(receipt)
        self._event("uv_detection", f"UV {role} inspection: {receipt['reason']}",
                    coral_id=coral["id"], fragment_id=fragment["id"], accepted=receipt["accepted"])
        if not receipt["accepted"]:
            self._reject_detection(worker, fragment, receipt["reason"])
        elif role == "recipient":
            worker["detection_status"] = "recipient_approved"
            self._begin_scan_navigation(worker, paired, "donor")
        else:
            fragment["detection_approved_at"] = self.time
            if not self._pair_detection_approved(worker, fragment):
                self._reject_detection(worker, fragment, "approval_invalidated")
                return
            worker["detection_status"] = "approved"
            self._clear_scan(worker)
            source = fragment["source_position"]
            worker.update(state="NAVIGATE_TO_PICKUP", manipulation_phase="approved_transit_to_pickup",
                          target=[source[0], source[1], max(.90, source[2]+.045+.55)], phase_progress=0.)

    def _pair_detection_approved(self, worker, fragment):
        """Recheck both recorded scenario receipts and current registry before action."""
        approved = fragment.get("detection_approved_at")
        if approved is None or approved > self.time:
            return False
        recipient = self._truth_by_id[worker["task_id"]]
        donor = self._truth_by_id[worker["donor_id"]]
        values = [recipient, donor, self.observations.get(recipient["id"], {}),
                  self.observations.get(donor["id"], {})]
        if ([v.get("health") for v in values] != ["bleached_alive", "healthy"]*2
                or not all(v.get("genotype_known") and v.get("genet_id") for v in values)
                or len({v.get("genet_id") for v in values} | {fragment.get("genet_id")}) != 1
                or len({v.get("species") for v in values} | {fragment.get("source_species")}) != 1):
            return False
        for role, coral, paired in (("recipient", recipient, donor), ("donor", donor, recipient)):
            receipt = fragment.get("detection_evidence", {}).get(role, {})
            if (not receipt.get("accepted") or receipt.get("mode") != "uv"
                    or receipt.get("role") != role or receipt.get("coral_id") != coral["id"]
                    or receipt.get("paired_colony_id") != paired["id"]
                    or receipt.get("fragment_id") != fragment["id"]
                    or receipt.get("timestamp", math.inf) > approved
                    or receipt.get("known_genet") != coral["genet_id"]
                    or receipt.get("known_species") != coral["species"]
                    or receipt not in self._detection_history):
                return False
        return True

    def _reject_detection(self, worker, fragment, reason):
        """Hold without harvesting; retain an already held fragment if invalidated."""
        self._clear_scan(worker)
        worker.update(state="DETECTION_REJECTED", detection_status="rejected",
                      detection_rejection_reason=reason, target=worker["position"][:],
                      manipulation_phase="detection_rejected", phase_progress=0.)
        if fragment["stage"] == "attached_to_donor":
            fragment.update(reserved_by=None, target_id=None)
            for coral in (self._truth_by_id[worker["task_id"]], self.observations[worker["task_id"]]):
                coral.update(task_status="detection_rejected", reserved_by=None)
            worker.update(carrying=False, gripper_open=1.)
        elif fragment["stage"] in ("grasped", "carried"):
            worker["gripper_open"] = 0.
        self._event("detection_rejected", f"Safe hold: {reason}; no further collection or placement",
                    coral_id=worker["task_id"], fragment_id=fragment["id"])

    def _settled(self, robot):
        return (robot["target"] is not None
                and distance(robot["position"], robot["target"]) < self.config["robot"]["attachment_position_tolerance"]
                and distance(robot["velocity"], [0, 0, 0]) < self.config["robot"]["attachment_speed_tolerance"])

    def _observe(self):
        for robot in self.robots:
            if not robot["available"]:
                continue
            for coral in self.corals:
                surface = [*coral["position"][:2], coral["height"] * 0.65]
                dz = robot["position"][2] - surface[2]
                horizontal = math.hypot(robot["position"][0] - surface[0], robot["position"][1] - surface[1])
                depth = distance(robot["position"], surface)
                cone = math.tan(math.radians(self.config["robot"]["camera_half_fov_degrees"]))
                if dz <= 0 or horizontal > dz * cone or depth > self.water["visibility"]:
                    continue
                if not self._line_clear(robot["position"], surface, margin=0.0, three_dimensional=True):
                    continue
                confidence = clamp(0.99 - 0.24 * depth / self.water["visibility"] - self.water["turbidity"] * 0.20, 0, 1)
                if confidence < 0.45:
                    continue
                if coral["id"] not in self.observations:
                    status = ("protected" if coral["health"] == "healthy" else
                              "eligible" if coral["health"] == "bleached_alive" and coral["substrate_suitable"] else
                              "monitor" if coral["health"] == "bleached_alive" else "excluded")
                    estimated = [coral["position"][0] + coral["_measurement_error"][0],
                                 coral["position"][1] + coral["_measurement_error"][1], 0.0]
                    self.observations[coral["id"]] = {"id": coral["id"], "position": estimated,
                        "health": coral["health"], "species": coral["species"], "height": coral["height"],
                        "morphology": coral["morphology"], "donor_capacity": coral["donor_capacity"],
                        "planting_point": copy.deepcopy(coral["planting_point"]),
                        "task_status": status, "confidence": confidence, "timestamp": self.time,
                        "source_robot": robot["id"], "reserved_by": None,
                        "source": "visibility_limited_synthetic_observation"}
                    if self._contact_mode:
                        self.observations[coral["id"]].update({key: copy.deepcopy(coral[key]) for key in
                            ("attachment_method", "genet_id", "genotype_known", "genotype_source", "genet_marker", "fluorescence_marker",
                             "contact_base", "contact_point", "contact_normal", "contact_fixture")})
                    coral["observed"] = True
                    coral["task_status"] = status
                    self._event("observation", f"{coral['id']} · {coral['health'].replace('_', ' ')} · {status}", coral_id=coral["id"])
                else:
                    obs = self.observations[coral["id"]]
                    obs["timestamp"] = self.time
                    obs["confidence"] = max(obs["confidence"], confidence)

    def _line_clear(self, a, b, margin=0.35, three_dimensional=False):
        dx, dy = b[0] - a[0], b[1] - a[1]
        denom = dx * dx + dy * dy
        for obstacle in self.obstacles:
            ox, oy, _ = obstacle["position"]
            t = clamp(((ox - a[0]) * dx + (oy - a[1]) * dy) / denom, 0, 1) if denom else 0
            close = math.hypot(a[0] + t * dx - ox, a[1] + t * dy - oy)
            if close < obstacle["radius"] + margin:
                if three_dimensional and a[2] + t * (b[2] - a[2]) > obstacle["height"]:
                    continue
                return False
        return True

    def _plan_path(self, start, goal):
        if self._line_clear(start, goal):
            return [goal[:]]
        # In the minimum world there is insufficient room for the legacy
        # horizontal survey detour outside the rubble. A survey leg already
        # above every solid obstacle can safely retain its altitude instead.
        if min(self.config["world"]["width"], self.config["world"]["length"]) < 10:
            ceiling = max(o["height"] for o in self.obstacles) + self.config["robot"]["radius"]
            if min(start[2], goal[2]) > ceiling:
                return [goal[:]]
        spacing = 0.4
        limit = 12
        def node(point):
            return (int(round(point[0] / spacing)), int(round(point[1] / spacing)))
        def point(cell):
            return [cell[0] * spacing, cell[1] * spacing, goal[2]]
        def free(cell):
            p = point(cell)
            return all(math.hypot(p[0] - o["position"][0], p[1] - o["position"][1]) >= o["radius"] + 0.38 for o in self.obstacles)
        source, target = node(start), node(goal)
        if not free(target):
            options = [(x, y) for x in range(-limit, limit + 1) for y in range(-limit, limit + 1) if free((x, y))]
            target = min(options, key=lambda cell: distance(point(cell), goal))
        queue = [(0.0, source)]
        costs, parents = {source: 0.0}, {}
        while queue:
            _, current = heapq.heappop(queue)
            if current == target:
                cells = [current]
                while current in parents:
                    current = parents[current]
                    cells.append(current)
                cells.reverse()
                path = [point(cell) for cell in cells[1:]]
                if self._line_clear(point(target), goal):
                    path.append(goal[:])
                return path or [goal[:]]
            for dx, dy in ((-1, 0), (1, 0), (0, -1), (0, 1), (-1, -1), (-1, 1), (1, -1), (1, 1)):
                nxt = current[0] + dx, current[1] + dy
                if abs(nxt[0]) > limit or abs(nxt[1]) > limit or not free(nxt):
                    continue
                if not self._line_clear(point(current), point(nxt), margin=0.32):
                    continue
                cost = costs[current] + math.hypot(dx, dy)
                if cost < costs.get(nxt, math.inf):
                    costs[nxt], parents[nxt] = cost, current
                    heapq.heappush(queue, (cost + math.hypot(nxt[0] - target[0], nxt[1] - target[1]), nxt))
        return []

    def _integrate(self, robot, dt):
        if not robot["available"]:
            robot["velocity"] = [0.0, 0.0, 0.0]
            return
        target = robot["target"] or robot["position"][:]
        if robot["_path_goal"] != target:
            robot["_path"] = self._plan_path(robot["position"], target)
            robot["_path_goal"] = target[:]
        path = robot["_path"]
        while len(path) > 1 and distance(robot["position"], path[0]) < 0.28:
            path.pop(0)
        waypoint = path[0] if path else robot["position"][:]
        cfg = self.config["robot"]
        error = [waypoint[i] - robot["position"][i] for i in range(3)]
        desired = [1.8 * e for e in error]
        speed = distance(desired, [0, 0, 0])
        if speed > cfg["max_speed"]:
            desired = [v * cfg["max_speed"] / speed for v in desired]
        # Reciprocal velocity repulsion is supplemented by a hard separation guard.
        for other in self.robots:
            if other is robot:
                continue
            separation = distance(robot["position"], other["position"])
            if 1e-6 < separation < 0.9:
                for axis in range(3):
                    desired[axis] += (robot["position"][axis] - other["position"][axis]) / separation * (0.9 - separation) * 1.4
        thrust = []
        forces = []
        for i in range(3):
            relative = robot["velocity"][i] - self.water["current"][i]
            drag = -cfg["linear_drag"][i] * relative - cfg["quadratic_drag"][i] * relative * abs(relative)
            # Feed-forward drag compensation makes steady station keeping possible.
            nominal = desired[i] - self.water["current"][i]
            compensation = cfg["linear_drag"][i] * nominal + cfg["quadratic_drag"][i] * nominal * abs(nominal)
            buoyancy = (self.water["density"] * cfg["displaced_volume"] - cfg["mass"]) * 9.81 if i == 2 else 0.0
            thrust.append(cfg["mass"] * 2.8 * (desired[i] - robot["velocity"][i]) + compensation - buoyancy)
            forces.append(drag + buoyancy)
        magnitude = distance(thrust, [0, 0, 0])
        if magnitude > cfg["max_thrust"]:
            thrust = [v * cfg["max_thrust"] / magnitude for v in thrust]
        velocity = [robot["velocity"][i] + (forces[i] + thrust[i]) / cfg["mass"] * dt for i in range(3)]
        next_position = [robot["position"][i] + velocity[i] * dt for i in range(3)]
        next_position[0] = clamp(next_position[0], -self.config["world"]["width"] / 2 + 0.15, self.config["world"]["width"] / 2 - 0.15)
        next_position[1] = clamp(next_position[1], -self.config["world"]["length"] / 2 + 0.15, self.config["world"]["length"] / 2 - 0.15)
        next_position[2] = clamp(next_position[2], 0.85, self.config["world"]["depth"] - 0.5)
        blocked = any(distance(next_position, other["position"]) < cfg["radius"] * 2 for other in self.robots if other is not robot)
        blocked = blocked or any(math.hypot(next_position[0] - o["position"][0], next_position[1] - o["position"][1]) < o["radius"] + cfg["radius"] and next_position[2] < o["height"] + cfg["radius"] for o in self.obstacles)
        if blocked:
            # Collision avoidance stopped a command; this is not counted as contact.
            robot["velocity"] = [0.0, 0.0, 0.0]
        else:
            robot["distance_travelled"] += distance(robot["position"], next_position)
            robot["position"], robot["velocity"] = next_position, velocity
        contact_heading = None
        if self._contact_mode and robot["role"] == "restoration" and robot.get("task_id"):
            contacting = robot["state"] in ("LOWER_FRAGMENT", "SECURE_FRAGMENT", "OPEN_GRIPPER",
                                            "RETRACT_GRIPPER", "VERIFY_ATTACHMENT")
            arriving = robot["state"] == "NAVIGATE_TO_SITE" and distance(robot["position"], target) < .45
            if contacting or arriving:
                normal = self._truth_by_id[robot["task_id"]]["contact_normal"]
                contact_heading = math.atan2(-normal[1], -normal[0])
        if (self._detection_required and robot.get("_scan_yaw") is not None
                and distance(robot["position"], target) < .45):
            contact_heading = robot["_scan_yaw"]
        if math.hypot(velocity[0], velocity[1]) > 0.06 or contact_heading is not None:
            heading = contact_heading if contact_heading is not None else math.atan2(velocity[1], velocity[0])
            angular_error = (heading - robot["yaw"] + math.pi) % (2 * math.pi) - math.pi
            robot["yaw"] += clamp(angular_error, -dt * 1.4, dt * 1.4)
        robot["_trail_clock"] += dt
        if robot["_trail_clock"] >= 0.5:
            robot["_trail_clock"] = 0.0
            robot["trail"].append(robot["position"][:])
            robot["trail"] = robot["trail"][-240:]

    def snapshot(self):
        def public(obj):
            return {key: copy.deepcopy(value) for key, value in obj.items() if not key.startswith("_")}
        attached = sum(coral["fragment_attached"] for coral in self.corals)
        verified = sum(coral["task_status"] == "verified" for coral in self.corals)
        observed = len(self.observations)
        eligible = sum(obs["task_status"] in ("eligible", "reserved") for obs in self.observations.values())
        remaining = sum(f["stage"] in ("attached_to_donor", "grasped") for f in self.fragments)
        available = sum(f["stage"] == "attached_to_donor" and f["reserved_by"] is None for f in self.fragments)
        metrics = {"observed": observed, "total_corals": len(self.corals),
                   "coverage": observed / len(self.corals), "eligible": eligible,
                   "attached": attached, "verified": verified, "inventory": remaining,
                   "donor_fragments_available": available, "donor_fragments_remaining": remaining,
                   "initial_fragment_count": len(self.fragments),
                   "collisions": self.collisions, "duplicate_assignments": self.duplicate_assignments,
                   "distance_travelled": sum(robot["distance_travelled"] for robot in self.robots),
                   "mission_time": self.time, "mission_complete": self.robots[1]["state"] == "COMPLETE",
                   "survey_progress": min(1.0, self._survey_index / len(self._survey_waypoints))}
        return {"time": self.time, "seed": self.config["seed"], "mode": "paused" if self.paused else "running",
                "paused": self.paused, "world": copy.deepcopy(self.config["world"]),
                "water": copy.deepcopy(self.water), "regions": copy.deepcopy(self.regions),
                "corals": [public(coral) for coral in self.corals],
                "robots": [public(robot) for robot in self.robots],
                "observations": list(copy.deepcopy(self.observations).values()),
                "obstacles": copy.deepcopy(self.obstacles), "fragments": [public(fragment) for fragment in self.fragments],
                "donor_stock": {"initial": len(self.fragments), "remaining": remaining, "available": available},
                "events": copy.deepcopy(self.events), "metrics": metrics,
                "assumptions": copy.deepcopy(self.config["assumptions"]),
                "attachment_method": self.config["mission"]["attachment_method"],
                **({"detection_required": True, "detection_history": copy.deepcopy(self._detection_history)}
                   if self._detection_required else {})}
