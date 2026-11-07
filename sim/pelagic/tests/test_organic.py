import math
import unittest

from reefsim.organic import generate_coral, generate_fragment
from reefsim.reef_landscape import build_reef_scenery, build_reef_foundation, _floor_height


class OrganicCoralTests(unittest.TestCase):
    def test_smooth_indexed_mesh_contract(self):
        for morphology in ("branching", "boulder"):
            with self.subTest(morphology=morphology):
                mesh = generate_coral(morphology, "healthy", .32, .65, 26)
                size = len(mesh["points"])
                self.assertGreater(size, 4000)
                self.assertLess(size, 30000)
                for field in ("normals", "colors", "uvs"):
                    self.assertEqual(len(mesh[field]), size)
                self.assertEqual(sum(mesh["counts"]), len(mesh["indices"]))
                self.assertTrue(all(0 <= index < size for index in mesh["indices"]))
                self.assertTrue(all(math.isfinite(v) for p in mesh["points"] for v in p))
                self.assertTrue(all(math.isfinite(v) for uv in mesh["uvs"] for v in uv))
                for normal in mesh["normals"]:
                    self.assertAlmostEqual(sum(v * v for v in normal), 1., places=5)
                self.assertGreater(max(p[2] for p in mesh["points"]), .60)
                self.assertLess(min(p[2] for p in mesh["points"]), .05)

    def test_seed_reproducibility_and_colour_states(self):
        first = generate_coral("boulder", "healthy", .3, .6, 9)
        self.assertEqual(first, generate_coral("boulder", "healthy", .3, .6, 9))
        self.assertNotEqual(first["points"], generate_coral("boulder", "healthy", .3, .6, 10)["points"])
        bleached = generate_coral("boulder", "bleached_alive", .3, .6, 9)
        dead = generate_coral("boulder", "dead", .3, .6, 9)
        # Bleaching preserves skeleton; dead skeleton has eroded surface pits.
        self.assertEqual(first["points"], bleached["points"])
        self.assertNotEqual(first["points"], dead["points"])
        brightness = lambda m: sum(sum(c) for c in m["colors"]) / len(m["colors"])
        self.assertGreater(brightness(bleached), brightness(first))
        self.assertGreater(brightness(bleached), brightness(dead))

    def test_curved_branching_has_normal_variation_and_bounded_dimensions(self):
        mesh = generate_coral("branching", "healthy", .32, .65, 1)
        self.assertGreater(len(set(tuple(round(v, 2) for v in n) for n in mesh["normals"])), 500)
        self.assertLess(max(abs(p[0]) for p in mesh["points"]), .65)
        self.assertLess(max(abs(p[1]) for p in mesh["points"]), .65)
        self.assertLessEqual(max(p[2] for p in mesh["points"]), .66)

    def test_invalid_inputs(self):
        for radius in (0, -1, float("nan"), float("inf")):
            with self.assertRaises(ValueError):
                generate_coral("branching", "healthy", radius, .6, 1)
        with self.assertRaises(ValueError):
            generate_coral("unknown", "healthy", .3, .6, 1)

    def test_fragment_is_one_clean_stem_without_mound_or_roots(self):
        mesh = generate_fragment(12)
        self.assertGreater(len(mesh["points"]), 500)
        self.assertLess(len(mesh["points"]), 3000)
        self.assertGreaterEqual(min(p[2] for p in mesh["points"]), -1e-6)
        low = [p for p in mesh["points"] if p[2] < .065]
        self.assertLess(max(math.hypot(p[0], p[1]) for p in low), .009)
        self.assertLess(max(abs(p[0]) for p in mesh["points"]), .04)
        self.assertEqual(mesh, generate_fragment(12))
        self.assertEqual(sum(mesh["counts"]), len(mesh["indices"]))
        self.assertTrue(all(0 <= i < len(mesh["points"]) for i in mesh["indices"]))

    def test_plating_and_low_detail_geometry(self):
        for morphology in ("branching", "boulder", "plating"):
            full = generate_coral(morphology, "healthy", .3, .25, 12)
            low = generate_coral(morphology, "healthy", .3, .25, 12, detail="low")
            self.assertLess(len(low["points"]), len(full["points"]))
            for mesh in (full, low):
                self.assertEqual(len(mesh["points"]), len(mesh["normals"]))
                self.assertEqual(len(mesh["points"]), len(mesh["uvs"]))
                self.assertTrue(all(math.isfinite(v) for p in mesh["points"] for v in p))
        self.assertEqual(generate_coral("plating", "healthy", .3, .2, 1),
                         generate_coral("tabular", "healthy", .3, .2, 1))

    def test_populated_reef_has_contrasting_zones_and_clear_operation_space(self):
        from reefsim.core import ReefSimulation
        sim = ReefSimulation()
        snapshot = sim.snapshot()
        scenery = build_reef_scenery(sim.config, snapshot)
        self.assertGreaterEqual(len(scenery), 450)
        self.assertEqual(scenery, build_reef_scenery(sim.config, snapshot))
        living = sum(c["health"] == "healthy" for c in scenery)
        dead = sum(c["health"] == "dead" for c in scenery)
        self.assertGreater(living, dead)
        self.assertGreater(sum(c["morphology"] == "plating" for c in scenery), 25)
        for c in scenery:
            self.assertTrue(c["display_only"])
            for main in snapshot["corals"]:
                self.assertGreaterEqual(math.hypot(c["position"][0] - main["position"][0],
                                                  c["position"][1] - main["position"][1]),
                                        main["radius"] + .18 + c["radius"] * .70 - 1e-6)



    def test_reef_pavement_is_connected_anchored_and_below_mounts(self):
        from reefsim.core import ReefSimulation
        sim = ReefSimulation()
        snapshot = sim.snapshot()
        mesh = build_reef_foundation(sim.config, snapshot, resolution=32)
        self.assertEqual(mesh, build_reef_foundation(sim.config, snapshot, resolution=32))
        self.assertEqual(len(mesh["points"]), 33*33)
        self.assertEqual(len(mesh["counts"]), 32*32)
        self.assertEqual(sum(mesh["counts"]), len(mesh["indices"]))
        self.assertEqual(len(mesh["normals"]), len(mesh["points"]))
        self.assertLess(max(p[2] for p in mesh["points"]), .08)
        for p, normal in zip(mesh["points"], mesh["normals"]):
            self.assertGreaterEqual(p[2], _floor_height(p[0], p[1]) - 1e-9)
            self.assertAlmostEqual(sum(v*v for v in normal), 1., places=6)
            self.assertGreater(normal[2], .8)
        self.assertTrue(all(0 <= i < len(mesh["points"]) for i in mesh["indices"]))

    def test_dead_branching_has_weathered_broken_crown(self):
        alive = generate_coral("branching", "healthy", .3, .6, 26, detail="low")
        dead = generate_coral("branching", "dead", .3, .6, 26, detail="low")
        self.assertLess(len(dead["points"]), len(alive["points"]))
        self.assertLess(max(p[2] for p in dead["points"]), max(p[2] for p in alive["points"])*.9)
        self.assertEqual(dead, generate_coral("branching", "dead", .3, .6, 26, detail="low"))

if __name__ == "__main__":
    unittest.main()
