import math
import unittest

from reefsim.organic import generate_fragment
from reefsim.pocillopora import generate_pocillopora, generate_contact_fragment


class PocilloporaTests(unittest.TestCase):
    def assert_mesh(self, mesh, limit):
        size = len(mesh["points"])
        self.assertLess(size, limit)
        self.assertEqual(sum(mesh["counts"]), len(mesh["indices"]))
        self.assertTrue(all(0 <= i < size for i in mesh["indices"]))
        for key in ("normals", "colors", "uvs"):
            self.assertEqual(len(mesh[key]), size)
        self.assertTrue(all(math.isfinite(v) for key in ("points", "normals", "colors", "uvs")
                            for row in mesh[key] for v in row))
        self.assertTrue(all(abs(sum(v*v for v in n) - 1.) < 1e-6 for n in mesh["normals"]))

    def test_colonies_are_bounded_seeded_and_keep_bleached_structure(self):
        healthy = generate_pocillopora("healthy", .35, .55, 26)
        bleached = generate_pocillopora("bleached_alive", .35, .55, 26)
        dead = generate_pocillopora("dead", .35, .55, 26)
        self.assertEqual(healthy, generate_pocillopora("healthy", .35, .55, 26))
        self.assertEqual(healthy["points"], bleached["points"])
        self.assertNotEqual(healthy["points"], dead["points"])
        self.assertNotEqual(healthy["points"], generate_pocillopora("healthy", .35, .55, 27)["points"])
        for mesh in (healthy, bleached, dead):
            self.assert_mesh(mesh, 30000)
            self.assertGreaterEqual(min(p[2] for p in mesh["points"]), 0.)
            self.assertLessEqual(max(p[2] for p in mesh["points"]), .55000001)
            self.assertLessEqual(max(math.hypot(p[0], p[1]) for p in mesh["points"]), .35000001)
        mean = lambda m: sum(sum(c) for c in m["colors"]) / len(m["colors"])
        self.assertGreater(mean(bleached), mean(healthy))
        self.assertGreater(mean(healthy), mean(dead))

    def test_contact_fragment_preserves_grasp_stem_exactly(self):
        for seed in (12, 26, 99):
            original = generate_fragment(seed, .14, .025)
            contact = generate_contact_fragment(seed)
            self.assert_mesh(contact, 6000)
            self.assertEqual(contact, generate_contact_fragment(seed))
            for i, point in enumerate(original["points"]):
                if point[2] <= .075:
                    self.assertEqual(point, contact["points"][i])
                    self.assertEqual(original["normals"][i], contact["normals"][i])
            added = contact["points"][len(original["points"]):]
            self.assertTrue(all(p[2] > .075 for p in added))
            self.assertGreaterEqual(min(p[2] for p in contact["points"]), 0.)
            self.assertAlmostEqual(max(p[2] for p in contact["points"]), .14)
            self.assertLessEqual(max(abs(v) for p in contact["points"] for v in p[:2]), .045)
            self.assertLessEqual(max(p[0] for p in contact["points"]) - min(p[0] for p in contact["points"]), .10)
            self.assertLessEqual(max(p[1] for p in contact["points"]) - min(p[1] for p in contact["points"]), .10)
            # Upper-crown expansion is visible, while the pinch diameter stays fixed.
            upper = lambda m: max(math.hypot(p[0], p[1]) for p in m["points"] if p[2] > .09)
            self.assertGreater(upper(contact), upper(original) * 1.25)

    def test_invalid_dimensions_and_health(self):
        for radius, height in ((0., .5), (.3, 0.), (math.nan, .5), (.3, math.inf)):
            with self.assertRaises(ValueError):
                generate_pocillopora("healthy", radius, height, 26)
        with self.assertRaises(ValueError):
            generate_pocillopora("unknown", .3, .5, 26)
        with self.assertRaises(ValueError):
            generate_contact_fragment(26, height=.07)


if __name__ == "__main__":
    unittest.main()
