from pathlib import Path
import json
import math
import unittest

from reefsim.config import load_config
from reefsim.core import ReefSimulation, distance


def finish(sim, seconds=400):
    for _ in range(int(seconds * 2)):
        sim.step(0.5)
        if sim.snapshot()["metrics"]["mission_complete"]:
            break
    return sim.snapshot()


class ReefMissionTests(unittest.TestCase):
    def test_complete_mission_preserves_biological_state_and_stock(self):
        sim = ReefSimulation()
        initial_health = {c["id"]: c["health"] for c in sim.corals}
        snapshot = finish(sim)
        self.assertTrue(snapshot["metrics"]["mission_complete"])
        self.assertEqual(snapshot["metrics"]["verified"], 4)
        self.assertEqual(snapshot["metrics"]["observed"], 24)
        self.assertEqual(snapshot["metrics"]["inventory"], 2)
        self.assertEqual(snapshot["metrics"]["duplicate_assignments"], 0)
        self.assertEqual(snapshot["metrics"]["collisions"], 0)
        self.assertEqual(len({c["fragment_id"] for c in snapshot["corals"] if c["fragment_attached"]}), 4)
        self.assertNotIn("nursery", snapshot)
        self.assertEqual(snapshot["metrics"]["donor_fragments_remaining"], 2)
        for fragment in snapshot["fragments"]:
            donor = sim._truth_by_id[fragment["donor_id"]]
            self.assertEqual(donor["health"], "healthy")
            if fragment["stage"] == "placed":
                target = sim._truth_by_id[fragment["target_id"]]
                self.assertEqual(target["health"], "bleached_alive")
                self.assertEqual(fragment["position"], target["planting_point"])
        for coral in snapshot["corals"]:
            self.assertEqual(coral["health"], initial_health[coral["id"]])
            if coral["fragment_attached"]:
                self.assertEqual(coral["region_id"], "bleached")
                self.assertTrue(coral["substrate_suitable"])

    def test_only_bleached_living_colonies_can_be_recipients(self):
        config = load_config()
        # Even an erroneous planting policy cannot make a healthy/dead colony
        # eligible. Biological state is the required recipient predicate.
        for region in config["regions"]:
            if region["health"] != "bleached_alive":
                region["policy"] = "plant"
        sim = ReefSimulation(config)
        self.assertEqual(sum(c["substrate_suitable"] for c in sim.corals), 4)
        for coral in sim.corals:
            if coral["substrate_suitable"]:
                self.assertEqual(coral["health"], "bleached_alive")
            else:
                self.assertIsNone(coral["planting_point"])
        snapshot = finish(sim)
        self.assertEqual(snapshot["metrics"]["verified"], 4)
        for observation in snapshot["observations"]:
            if observation["health"] == "healthy":
                self.assertEqual(observation["task_status"], "protected")
            elif observation["health"] == "dead":
                self.assertEqual(observation["task_status"], "excluded")
                self.assertIsNone(observation["reserved_by"])

    def test_same_seed_and_commands_reproduce_mission(self):
        first, second = ReefSimulation(), ReefSimulation()
        for _ in range(100):
            first.step(0.1)
            second.step(0.1)
        self.assertEqual(first.snapshot(), second.snapshot())
        third = ReefSimulation({"seed": 7})
        self.assertNotEqual(first.corals[0]["position"], third.corals[0]["position"])

    def test_mounts_clear_all_colonies_and_rocks_in_supported_layouts(self):
        for seed in (26, 42):
            for size in (8, 10):
                with self.subTest(seed=seed, world_size=size):
                    sim = ReefSimulation({"seed": seed, "world": {"width": size, "length": size}})
                    mounts = [c for c in sim.corals if c["substrate_suitable"]]
                    self.assertEqual(len(mounts), 4)
                    for target in mounts:
                        point = target["planting_point"]
                        region = next(r for r in sim.regions if r["id"] == target["region_id"])
                        self.assertEqual(target["health"], "bleached_alive")
                        self.assertEqual(region["policy"], "plant")
                        self.assertEqual(point[2], .075)
                        self.assertLessEqual(abs(point[0]), size / 2 - .5)
                        self.assertLessEqual(abs(point[1]), size / 2 - .5)
                        self.assertLessEqual(distance(point[:2], region["center"][:2]), region["radius"] - .12)
                        # The entire wrist workspace clears every colony,
                        # including the bleached living recipient itself.
                        for occupied in sim.corals + sim.obstacles:
                            self.assertGreaterEqual(distance(point[:2], occupied["position"][:2]), occupied["radius"] + .55 - 1e-9)
                        for other in mounts:
                            if other is not target:
                                self.assertGreaterEqual(distance(point[:2], other["planting_point"][:2]), .70 - 1e-9)

    def test_clear_mount_layouts_complete_with_reachable_gripper(self):
        for seed in (26, 42):
            for size in (8, 10):
                with self.subTest(seed=seed, world_size=size):
                    sim = ReefSimulation({"seed": seed, "world": {"width": size, "length": size}})
                    for _ in range(8000):
                        sim.step(.05)
                        worker = sim.robots[1]
                        yaw = worker["yaw"]
                        shoulder = [worker["position"][0] + .17 * math.cos(yaw),
                                    worker["position"][1] + .17 * math.sin(yaw), worker["position"][2] - .12]
                        self.assertLessEqual(distance(shoulder, worker["gripper_world"]), .72)
                        if sim.snapshot()["metrics"]["mission_complete"]:
                            break
                    snapshot = sim.snapshot()
                    self.assertTrue(snapshot["metrics"]["mission_complete"])
                    self.assertEqual(snapshot["metrics"]["verified"], 4)
                    self.assertEqual(snapshot["metrics"]["observed"], 24)
                    self.assertEqual(snapshot["metrics"]["collisions"], 0)
                    self.assertEqual(snapshot["metrics"]["donor_fragments_remaining"], 2)

    def test_observations_are_range_limited_and_separate_from_truth(self):
        sim = ReefSimulation({"water": {"visibility": 0.5}})
        self.assertEqual(len(sim.corals), 24)
        self.assertEqual(sim.observations, {})
        sim._observe()
        self.assertEqual(sim.observations, {})
        sim.command({"action": "set_water", "visibility": 4.5})
        sim._observe()
        self.assertGreater(len(sim.observations), 0)
        self.assertLess(len(sim.observations), len(sim.corals))
        obs = next(iter(sim.observations.values()))
        truth = sim._truth_by_id[obs["id"]]
        self.assertIsNot(obs, truth)
        self.assertNotEqual(obs["position"], truth["position"])
        self.assertIn("synthetic", obs["source"])

    def test_water_conditions_change_survey_behaviour(self):
        clear = ReefSimulation()
        murky = ReefSimulation({"water": {"visibility": 1.6}})
        clear.step(4)
        murky.step(4)
        self.assertLess(murky.robots[0]["position"][2], clear.robots[0]["position"][2])
        self.assertNotEqual(len(clear.observations), len(murky.observations))

    def test_pause_and_reset(self):
        sim = ReefSimulation()
        sim.step(2)
        sim.command({"action": "pause"})
        snapshot = sim.snapshot()
        sim.step(20)
        self.assertEqual(sim.snapshot(), snapshot)
        sim.command({"action": "resume"})
        sim.step(1)
        self.assertGreater(sim.time, snapshot["time"])
        sim.command({"action": "reset"})
        self.assertEqual(sim.time, 0)
        self.assertEqual(len(sim.fragments), 6)
        self.assertTrue(all(f["stage"] == "attached_to_donor" for f in sim.fragments))
        self.assertEqual(sim.observations, {})

    def test_worker_disable_retains_fragment_and_reservation_then_resumes(self):
        sim = ReefSimulation()
        for _ in range(200):
            sim.step(0.5)
            if sim.robots[1]["carrying"]:
                break
        worker = sim.robots[1]
        self.assertTrue(worker["carrying"])
        task_id, inventory, position = worker["task_id"], sim.snapshot()["metrics"]["inventory"], worker["position"][:]
        fragment_before = sim._fragments_by_id[worker["fragment_id"]]["position"][:]
        sim.command({"action": "set_robot_available", "robot_id": worker["id"], "available": False})
        sim.step(10)
        self.assertEqual(worker["position"], position)
        self.assertEqual(worker["task_id"], task_id)
        self.assertTrue(worker["carrying"])
        self.assertEqual(sim.snapshot()["metrics"]["inventory"], inventory)
        self.assertEqual(sim._fragments_by_id[worker["fragment_id"]]["position"], fragment_before)
        self.assertEqual(sim.observations[task_id]["reserved_by"], worker["id"])
        sim.command({"action": "set_robot_available", "robot_id": worker["id"], "available": True})
        self.assertEqual(finish(sim)["metrics"]["verified"], 4)

    def test_stock_is_conserved_at_every_step(self):
        sim = ReefSimulation({"donors": {"max_fragments": 2}})
        identities = {f["id"] for f in sim.fragments}
        for _ in range(600):
            sim.step(0.5)
            self.assertEqual({f["id"] for f in sim.fragments}, identities)
            remaining = sum(f["stage"] in ("attached_to_donor", "grasped") for f in sim.fragments)
            moving = sum(f["stage"] == "carried" for f in sim.fragments)
            placed = sum(f["stage"] == "placed" for f in sim.fragments)
            self.assertEqual(remaining + moving + placed, 2)
            self.assertEqual(sim.snapshot()["metrics"]["inventory"], remaining)
            for coral in sim.corals:
                if coral["health"] != "bleached_alive":
                    self.assertIsNone(coral["reserved_by"])
                    self.assertFalse(coral["fragment_attached"])
            for fragment in sim.fragments:
                if fragment["target_id"] is not None:
                    self.assertEqual(sim._truth_by_id[fragment["target_id"]]["health"], "bleached_alive")
        self.assertEqual(sum(c["fragment_attached"] for c in sim.corals), 2)
        self.assertEqual(sim.robots[1]["state"], "NO_STOCK")

    def test_grasp_carry_release_is_continuous_and_keeps_one_fragment(self):
        sim = ReefSimulation()
        initial = {f["id"]: (f["radius"], f["height"], f["seed"], f["donor_id"]) for f in sim.fragments}
        previous = {f["id"]: f["position"][:] for f in sim.fragments}
        placed_positions = {}
        previous_stage = {f["id"]: f["stage"] for f in sim.fragments}
        previous_yaw = {f["id"]: f["yaw"] for f in sim.fragments}
        phases = []
        for _ in range(5000):
            sim.step(.05)
            robot = sim.robots[1]
            if not phases or phases[-1] != robot["state"]:
                phases.append(robot["state"])
            self.assertEqual(set(initial), {f["id"] for f in sim.fragments})
            for fragment in sim.fragments:
                self.assertEqual((fragment["radius"], fragment["height"], fragment["seed"], fragment["donor_id"]), initial[fragment["id"]])
                self.assertLess(distance(previous[fragment["id"]], fragment["position"]), .09)
                if previous_stage[fragment["id"]] != fragment["stage"]:
                    self.assertLess(distance(previous[fragment["id"]], fragment["position"]), .005)
                    yaw_delta = (fragment["yaw"] - previous_yaw[fragment["id"]] + math.pi) % (2 * math.pi) - math.pi
                    self.assertLess(abs(yaw_delta), .005)
                yaw_step = (fragment["yaw"] - previous_yaw[fragment["id"]] + math.pi) % (2 * math.pi) - math.pi
                self.assertLess(abs(yaw_step), .071)
                previous[fragment["id"]] = fragment["position"][:]
                previous_stage[fragment["id"]] = fragment["stage"]
                previous_yaw[fragment["id"]] = fragment["yaw"]
                if fragment["stage"] == "grasped":
                    self.assertEqual(robot["gripper_open"], 0.)
                    self.assertFalse(robot["carrying"])
                    self.assertEqual(fragment["position"], fragment["source_position"])
                if fragment["stage"] == "carried":
                    self.assertTrue(robot["carrying"])
                    self.assertEqual(robot["fragment_id"], fragment["id"])
                    self.assertLess(distance(robot["gripper_world"], [*fragment["position"][:2], fragment["position"][2] + .045]), 1e-9)
                    if robot["state"] != "OPEN_GRIPPER":
                        self.assertEqual(robot["gripper_open"], 0.)
                if fragment["stage"] == "placed":
                    placed_positions.setdefault(fragment["id"], fragment["position"][:])
                    self.assertEqual(fragment["position"], placed_positions[fragment["id"]])
                    if robot["fragment_id"] == fragment["id"]:
                        self.assertFalse(robot["carrying"])
                        self.assertEqual(robot["gripper_open"], 1.)
            if robot["state"] not in ("WAIT_FOR_MAP", "COMPLETE", "PLAN", "NO_STOCK"):
                yaw = robot["yaw"]
                shoulder = [robot["position"][0] + .17 * math.cos(yaw), robot["position"][1] + .17 * math.sin(yaw), robot["position"][2] - .12]
                self.assertLessEqual(distance(shoulder, robot["gripper_world"]), .72)
            if sim.snapshot()["metrics"]["mission_complete"]:
                break
        required = ["APPROACH_FRAGMENT", "CLOSE_GRIPPER", "DETACH_FRAGMENT", "RETRACT_FRAGMENT",
                    "NAVIGATE_TO_SITE", "LOWER_FRAGMENT", "SECURE_FRAGMENT", "OPEN_GRIPPER",
                    "RETRACT_GRIPPER", "VERIFY_ATTACHMENT"]
        first = [phases.index(state) for state in required]
        self.assertEqual(first, sorted(first))
        self.assertEqual(len(placed_positions), 4)

    def test_strong_current_stays_finite_and_inside_world(self):
        sim = ReefSimulation({"water": {"current": [1.0, -1.0, 0.5]}})
        for _ in range(300):
            sim.step(0.5)
            for robot in sim.robots:
                self.assertTrue(all(math.isfinite(v) for v in robot["position"] + robot["velocity"]))
                self.assertLessEqual(abs(robot["position"][0]), 4.85)
                self.assertLessEqual(abs(robot["position"][1]), 4.85)
                self.assertGreaterEqual(robot["position"][2], 0.85)
            self.assertGreaterEqual(distance(sim.robots[0]["position"], sim.robots[1]["position"]), 0.56 - 1e-9)
        json.dumps(sim.snapshot(), allow_nan=False)

    def test_path_planner_routes_around_rock(self):
        sim = ReefSimulation()
        start, goal = [-2, -0.1, 1.4], [2, -0.1, 1.4]
        self.assertFalse(sim._line_clear(start, goal))
        path = sim._plan_path(start, goal)
        self.assertGreater(len(path), 1)
        last = start
        for waypoint in path:
            self.assertTrue(sim._line_clear(last, waypoint, margin=0.28))
            last = waypoint
        self.assertEqual(path[-1], goal)

    def test_nonfinite_and_invalid_water_rejected_without_mutation(self):
        sim = ReefSimulation()
        original = sim.water.copy()
        invalid = [
            {"visibility": float("nan")}, {"visibility": float("inf")},
            {"visibility": "murky"}, {"visibility": True},
            {"turbidity": float("nan")}, {"current": [float("nan"), 0, 0]},
            {"current": [0, float("inf"), 0]}, {"current": "bad"}, {"current": None},
            {"current": [0, 0]}, {"current": [2, 0, 0]},
        ]
        for updates in invalid:
            with self.subTest(updates=updates):
                with self.assertRaises(ValueError):
                    sim.command({"action": "set_water", **updates})
                self.assertEqual(sim.water, original)

    def test_json_overlay_and_snapshot_contract(self):
        sim = ReefSimulation(load_config(Path(__file__).resolve().parents[1] / "configs/reef.json"))
        payload = json.loads(json.dumps(sim.snapshot(), allow_nan=False))
        self.assertTrue({"time", "water", "regions", "corals", "robots", "observations", "metrics", "events"} <= payload.keys())
        with self.assertRaises(ValueError):
            sim.step(float("nan"))
        with self.assertRaises(ValueError):
            sim.step(-1)


if __name__ == "__main__":
    unittest.main()
