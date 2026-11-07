import math
import unittest

from reefsim.reef_substrate import generate_reef_rock


class ReefSubstrateTests(unittest.TestCase):
    def test_seeded_indexed_mesh_is_finite_and_within_geometry_budget(self):
        for detail, maximum in (("medium", 4000), ("low", 300)):
            mesh = generate_reef_rock(.5, .7, 26, detail)
            self.assertEqual(mesh, generate_reef_rock(.5, .7, 26, detail))
            self.assertNotEqual(mesh["points"], generate_reef_rock(.5, .7, 27, detail)["points"])
            count = len(mesh["points"])
            self.assertLess(count, maximum)
            for key in ("normals", "colors", "uvs"):
                self.assertEqual(len(mesh[key]), count)
            self.assertEqual(sum(mesh["counts"]), len(mesh["indices"]))
            self.assertTrue(all(0 <= i < count for i in mesh["indices"]))
            self.assertTrue(all(math.isfinite(v) for key in ("points", "normals", "colors", "uvs")
                                for row in mesh[key] for v in row))
            self.assertTrue(all(abs(sum(v*v for v in normal) - 1.) < 1e-6 for normal in mesh["normals"]))

    def test_all_shapes_preserve_obstacle_bounds_and_ground_contact(self):
        for radius, height in ((.025, .012), (.5, .7), (.8, .2), (.2, .9)):
            for seed in range(6):
                mesh = generate_reef_rock(radius, height, seed)
                self.assertGreaterEqual(min(p[2] for p in mesh["points"]), 0.)
                self.assertAlmostEqual(max(p[2] for p in mesh["points"]), height)
                self.assertLessEqual(max(math.hypot(p[0], p[1]) for p in mesh["points"]), radius + 1e-12)
                self.assertGreater(sum(p[2] == 0. for p in mesh["points"]), 64)
                # Asymmetry is substantive, not just a different texture.
                extents = [max(p[i] for p in mesh["points"]) + min(p[i] for p in mesh["points"])
                           for i in (0, 1)]
                self.assertGreater(max(abs(e) for e in extents), radius * .005)

    def test_face_winding_agrees_with_authored_outward_normals(self):
        mesh = generate_reef_rock(.5, .6, 26)
        offset = 0
        for count in mesh["counts"]:
            ids = mesh["indices"][offset:offset + count]
            offset += count
            a, b, c = [mesh["points"][i] for i in ids[:3]]
            u, v = [b[i] - a[i] for i in range(3)], [c[i] - a[i] for i in range(3)]
            face = (u[1]*v[2] - u[2]*v[1], u[2]*v[0] - u[0]*v[2], u[0]*v[1] - u[1]*v[0])
            normal = [sum(mesh["normals"][i][axis] for i in ids) / count for axis in range(3)]
            self.assertGreater(sum(face[i] * normal[i] for i in range(3)), -1e-10)

    def test_invalid_parameters_are_rejected(self):
        for value in (0., -1., math.inf, math.nan, True, 101.):
            with self.assertRaises(ValueError):
                generate_reef_rock(value, .5, 26)
            with self.assertRaises(ValueError):
                generate_reef_rock(.5, value, 26)
        with self.assertRaises(ValueError):
            generate_reef_rock(.5, .5, 26, "unknown")


if __name__ == "__main__":
    unittest.main()
