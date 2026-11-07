import copy
import math
from pathlib import Path
import unittest

from reefsim.config import load_config
from reefsim.core import ReefSimulation, distance
from reefsim.natural_contact import SurfaceQuery, closest_point_on_triangle
from reefsim.pocillopora_scan import generate_pocillopora_scan
from reefsim.pocillopora import generate_contact_fragment


ROOT = Path(__file__).resolve().parents[1]


def finish(sim, limit=240.):
    while sim.time < limit:
        sim.step(.05)
        if sim.robots[1]["state"] in ("COMPLETE", "NO_COMPATIBLE_DONOR"):
            break
    return sim.snapshot()


class ContactGraftTests(unittest.TestCase):
    def test_contact_fixture_is_tangent_and_only_owner_has_contact_exception(self):
        for seed in (26, 42):
            sim = ReefSimulation({"seed": seed, "mission": {"attachment_method": "same_genet_contact"}})
            sites = [c for c in sim.corals if c["substrate_suitable"]]
            self.assertEqual(len(sites), 4)
            for coral in sites:
                self.assertEqual(coral["health"], "bleached_alive")
                self.assertEqual(coral["morphology"], "branching")
                self.assertEqual(coral["species"], "pocillopora_damicornis_proxy")
                self.assertEqual(coral["planting_point"], coral["contact_base"])
                base, point, normal, fixture = (coral[k] for k in
                    ("contact_base", "contact_point", "contact_normal", "contact_fixture"))
                self.assertAlmostEqual(sum(x*x for x in normal), 1.)
                self.assertAlmostEqual(point[2] - base[2], .02)
                self.assertEqual(fixture["kind"], "natural_branch")
                self.assertNotIn("recipient_stem_base", fixture)
                self.assertAlmostEqual(distance(base[:2], point[:2]), fixture["donor_contact_radius"])
                self.assertLessEqual(distance(point[:2], coral["position"][:2]), coral["radius"])
                index = sim.corals.index(coral)
                mesh = generate_pocillopora_scan(coral["health"],coral["radius"],coral["height"],seed+index*813)
                triangle_index = fixture["source_triangle_index"]
                triangle = [[mesh["points"][mesh["indices"][triangle_index*3+j]][k]+coral["position"][k]
                             for k in range(3)] for j in range(3)]
                self.assertEqual(triangle, fixture["contact_triangle_world"])
                self.assertLess(distance(point, closest_point_on_triangle(point,*triangle)), 1e-9)
                self.assertLess(distance(base, fixture["support_point"]), .020)
                self.assertEqual(fixture["recipient_id"], coral["id"])
                for blocker in [c for c in sim.corals if c is not coral] + sim.obstacles:
                    self.assertGreaterEqual(distance(base[:2], blocker["position"][:2]), blocker["radius"] + .55 - 1e-8)
                for other in sites:
                    if other is not coral:
                        self.assertGreaterEqual(distance(base[:2], other["contact_base"][:2]), .70 - 1e-8)

    def test_full_contact_mission_preserves_genet_health_stock_and_pose_continuity(self):
        self._assert_full_contact_mission(ROOT / "configs" / "contact_graft.json")

    def test_hero_mesh_mission_contacts_actual_high_resolution_surface(self):
        self._assert_full_contact_mission(ROOT / "configs" / "natural_reef.json")

    def _assert_full_contact_mission(self, config):
        sim = ReefSimulation(config)
        original_health = {c["id"]: c["health"] for c in sim.corals}
        original_fragments = {f["id"]: (f["seed"], f["height"], f["radius"], f["genet_id"]) for f in sim.fragments}
        previous_positions = {f["id"]: f["position"][:] for f in sim.fragments}
        seen = set()
        while sim.time < 240:
            sim.step(.05)
            worker = sim.robots[1]
            seen.add(worker["state"])
            yaw = worker["yaw"]
            shoulder = [worker["position"][0] + .17 * math.cos(yaw),
                        worker["position"][1] + .17 * math.sin(yaw), worker["position"][2] - .12]
            self.assertLessEqual(distance(shoulder, worker["gripper_world"]), .72)
            if worker["state"] in ("LOWER_FRAGMENT", "SECURE_FRAGMENT", "OPEN_GRIPPER", "RETRACT_GRIPPER", "VERIFY_ATTACHMENT"):
                recipient = sim._truth_by_id[worker["task_id"]]
                self.assertGreaterEqual(distance(worker["position"][:2], recipient["position"][:2]),
                                        recipient["radius"] + sim.config["robot"]["radius"])
            for fragment in sim.fragments:
                self.assertEqual((fragment["seed"], fragment["height"], fragment["radius"], fragment["genet_id"]),
                                 original_fragments[fragment["id"]])
                self.assertLess(distance(fragment["position"], previous_positions[fragment["id"]]), .15)
                previous_positions[fragment["id"]] = fragment["position"][:]
                if fragment["stage"] == "carried":
                    if worker["state"] != "OPEN_GRIPPER":
                        self.assertLessEqual(worker["gripper_open"], .05)
                    self.assertLess(distance(fragment["position"],
                                             [*worker["gripper_world"][:2], worker["gripper_world"][2] - .045]), 1e-8)
            if worker["state"] == "COMPLETE":
                break
        state = sim.snapshot()
        self.assertTrue(state["metrics"]["mission_complete"])
        self.assertEqual(state["metrics"]["verified"], 4)
        self.assertEqual(state["metrics"]["inventory"], 2)
        self.assertEqual(state["metrics"]["observed"], 24)
        self.assertEqual(state["metrics"]["collisions"], 0)
        self.assertEqual(state["metrics"]["duplicate_assignments"], 0)
        self.assertTrue({"CLOSE_GRIPPER", "SECURE_FRAGMENT", "OPEN_GRIPPER", "RETRACT_GRIPPER"} <= seen)
        for coral in sim.corals:
            self.assertEqual(coral["health"], original_health[coral["id"]])
            if coral["fragment_attached"]:
                fragment = sim._fragments_by_id[coral["fragment_id"]]
                donor = sim._truth_by_id[fragment["donor_id"]]
                self.assertEqual(coral["health"], "bleached_alive")
                self.assertEqual(donor["health"], "healthy")
                self.assertEqual(coral["genet_id"], donor["genet_id"])
                self.assertEqual(coral["genet_id"], fragment["genet_id"])
                self.assertEqual(fragment["position"], coral["contact_base"])
                fixture = coral["contact_fixture"]
                detail = fixture["source_mesh_detail"]
                self.assertEqual(detail, "hero" if sim.config.get("render", {}).get("realistic_tissue", False) else "standard")
                options = {} if detail == "standard" else {"detail": detail}
                mesh = generate_pocillopora_scan(coral["health"],coral["radius"],coral["height"],fixture["source_mesh_seed"],**options)
                self.assertEqual(len(mesh["indices"])//3, fixture["source_triangle_count"])
                if detail == "hero":
                    self.assertGreater(fixture["source_triangle_count"], 100000)
                triangle_index = fixture["source_triangle_index"]
                actual_triangle = [[mesh["points"][mesh["indices"][triangle_index*3+j]][k]+coral["position"][k]
                                    for k in range(3)] for j in range(3)]
                self.assertEqual(actual_triangle, fixture["contact_triangle_world"])
                surface = SurfaceQuery([[p[k]+coral["position"][k] for k in range(3)] for p in mesh["points"]],mesh["indices"])
                cutting = generate_contact_fragment(fragment["seed"],fragment["height"],fragment["radius"])
                sine, cosine = math.sin(fragment["yaw"]),math.cos(fragment["yaw"])
                gaps = []
                upper_gaps = []
                for p in cutting["points"]:
                    q = [fragment["position"][0]+cosine*p[0]-sine*p[1],
                         fragment["position"][1]+sine*p[0]+cosine*p[1],fragment["position"][2]+p[2]]
                    if .010<=p[2]<=.035 or p[2]>=.065:
                        nearest=surface.nearest(q,radius=.015)
                        if nearest:
                            (gaps if p[2]<=.035 else upper_gaps).append(nearest["signed_distance"])
                self.assertTrue(gaps)
                self.assertGreaterEqual(min(gaps), -.003)
                self.assertLessEqual(min(gaps), fixture["contact_tolerance_m"])
                self.assertTrue(all(gap>=-.001 for gap in upper_gaps), "Crown intersects recipient away from contact patch")
                self.assertTrue(coral["graft_contact_secured"])
                self.assertEqual(coral["biological_recovery"], "pending_not_simulated")
            elif coral["health"] == "dead":
                self.assertEqual(coral["task_status"], "excluded")
                self.assertIsNone(coral["reserved_by"])

    def test_unknown_and_mismatched_genets_hold_without_harvesting(self):
        targets = [f"coral-{i:03d}" for i in range(7, 11)]
        for value in (None, "UNRELATED-GENET"):
            with self.subTest(genet=value):
                sim = ReefSimulation({"mission": {"attachment_method": "same_genet_contact",
                    "genet_assignments": {identifier: value for identifier in targets}}})
                state = finish(sim)
                self.assertEqual(state["robots"][1]["state"], "NO_COMPATIBLE_DONOR")
                self.assertFalse(state["metrics"]["mission_complete"])
                self.assertEqual(state["metrics"]["verified"], 0)
                self.assertEqual(state["metrics"]["inventory"], 6)
                self.assertTrue(all(f["stage"] == "attached_to_donor" and f["reserved_by"] is None for f in sim.fragments))

    def test_planner_requires_observed_donor_genet_not_truth_or_colour(self):
        sim = ReefSimulation({"mission": {"attachment_method": "same_genet_contact"}})
        sim._survey_index = len(sim._survey_waypoints)
        for coral in sim.corals:
            if coral["substrate_suitable"] or coral["donor_capacity"]:
                sim.observations[coral["id"]] = {"id": coral["id"], "position": coral["position"][:],
                    "health": coral["health"], "morphology": coral["morphology"], "species": coral["species"],
                    "task_status": "eligible" if coral["substrate_suitable"] else "protected", "confidence": 1.,
                    "genotype_known": coral["substrate_suitable"],
                    "genet_id": coral["genet_id"] if coral["substrate_suitable"] else None,
                    "fluorescence_marker": "red"}
        sim._update_mission(.05)
        self.assertEqual(sim.robots[1]["state"], "NO_COMPATIBLE_DONOR")
        self.assertTrue(all(f["reserved_by"] is None for f in sim.fragments))

    def test_baseline_and_invalid_mode_are_explicit(self):
        baseline = ReefSimulation()
        self.assertEqual(baseline.snapshot()["attachment_method"], "limestone_outplant")
        self.assertTrue(all("contact_fixture" not in c for c in baseline.corals))
        self.assertTrue(all(c["planting_point"][2] == .075 for c in baseline.corals if c["planting_point"]))
        with self.assertRaises(ValueError):
            load_config({"mission": {"attachment_method": "revive_dead"}})
        with self.assertRaises(ValueError):
            load_config({"mission": {"genet_assignments": {"coral-007": 123}}})


if __name__ == "__main__":
    unittest.main()
