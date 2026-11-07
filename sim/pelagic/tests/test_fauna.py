import copy
import math
import unittest

from reefsim.config import load_config
from reefsim.core import ReefSimulation
from reefsim.fauna import build_fauna, fauna_pose, fish_mesh


class FaunaTests(unittest.TestCase):
    def test_seeded_meshes_have_complete_finite_vertex_data(self):
        config = load_config()
        snapshot = ReefSimulation(config).snapshot()
        before = copy.deepcopy(snapshot)
        fish = build_fauna(config, snapshot)
        self.assertEqual(len(fish), 42)
        self.assertEqual(fish, build_fauna(config, snapshot))
        self.assertEqual(len({record["id"] for record in fish}), 42)
        self.assertEqual({record["school_id"] for record in fish}, {0, 1, 2})
        for record in fish:
            for key in ("body_mesh", "tail_mesh"):
                mesh = record[key]
                size = len(mesh["points"])
                self.assertEqual(len(mesh["normals"]), size)
                self.assertEqual(len(mesh["colors"]), size)
                self.assertEqual(len(mesh["uvs"]), size)
                self.assertEqual(sum(mesh["counts"]), len(mesh["indices"]))
                self.assertTrue(all(0 <= i < size for i in mesh["indices"]))
                self.assertTrue(all(math.isfinite(v) for group in ("points", "normals", "colors", "uvs") for item in mesh[group] for v in item))
                for normal in mesh["normals"]:
                    self.assertAlmostEqual(sum(v*v for v in normal), 1.)
                self.assertLess(size, 300)
        self.assertEqual(before, snapshot)

    def test_absolute_time_and_snapshot_determine_pose(self):
        config = load_config()
        snapshot = ReefSimulation(config).snapshot()
        fish = build_fauna(config, snapshot)[0]
        pose = fauna_pose(fish, 18.5, snapshot)
        for time in (42., 0., 99.1, -5.):
            fauna_pose(fish, time, snapshot)
        self.assertEqual(pose, fauna_pose(fish, 18.5, snapshot))
        self.assertNotEqual(pose["position"], fauna_pose(fish, 20.5, snapshot)["position"])
        with self.assertRaises(ValueError):
            fauna_pose(fish, math.nan, snapshot)

    def test_actual_mission_samples_keep_fish_out_of_worksites_and_solids(self):
        for width in (8., 10.):
            config = load_config({"world": {"width": width, "length": width}})
            simulation = ReefSimulation(config)
            fish = build_fauna(config, simulation.snapshot())
            for time in (0., 8., 25., 50., 80., 110., 145., 170.):
                while simulation.time + .025 < time:
                    simulation.step(.05)
                snapshot = simulation.snapshot()
                for record in fish:
                    pose = fauna_pose(record, time, snapshot)
                    x, y, z = pose["position"]
                    radius = record["bounding_radius"]
                    self.assertTrue(all(math.isfinite(v) for v in (x, y, z, pose["yaw"], pose["tail_angle"])))
                    self.assertLessEqual(abs(x), width/2-.35+1e-7)
                    self.assertLessEqual(abs(y), width/2-.35+1e-7)
                    self.assertGreaterEqual(z, .65-1e-7)
                    self.assertLessEqual(z, config["world"]["depth"]-.35+1e-7)
                    for item in snapshot["corals"] + snapshot["obstacles"]:
                        if z < item["position"][2]+item["height"]+radius+.16:
                            self.assertGreaterEqual(math.hypot(x-item["position"][0], y-item["position"][1]), item["radius"]+radius+.14-1e-6)
                    for target in snapshot["corals"]:
                        mount = target.get("planting_point")
                        if mount:
                            self.assertGreaterEqual(math.hypot(x-mount[0], y-mount[1]), .68+radius-1e-6)
                    for robot in snapshot["robots"]:
                        self.assertGreaterEqual(math.dist(pose["position"], robot["position"]), .50+radius-1e-6)

    def test_population_can_be_disabled(self):
        config = load_config({"render": {"fish_count": 0}})
        self.assertEqual(build_fauna(config, ReefSimulation(config).snapshot()), [])

    def test_full_cinematic_replay_has_no_teleports_or_coincident_fish(self):
        simulation = ReefSimulation(load_config("configs/cinematic.json"))
        fish = build_fauna(simulation.config, simulation.snapshot())
        previous = None
        for tick in range(3211):
            if tick:
                simulation.step(.05)
            snapshot = simulation.snapshot()
            positions = [fauna_pose(record, simulation.time, snapshot)["position"] for record in fish]
            if previous is not None:
                self.assertLess(max(math.dist(a, b) for a, b in zip(previous, positions)), .15,
                                f"Abrupt fish displacement at {simulation.time:g}s")
            for index, position in enumerate(positions):
                for other in positions[:index]:
                    self.assertGreater(math.dist(position, other), .18,
                                       f"Fish bodies coincide at {simulation.time:g}s")
            previous = positions


if __name__ == "__main__":
    unittest.main()
