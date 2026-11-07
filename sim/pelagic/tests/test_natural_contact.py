import math
import unittest

from reefsim.natural_contact import SurfaceQuery, closest_point_on_triangle


class NaturalSurfaceQueryTests(unittest.TestCase):
    def test_closest_points_cover_face_edges_and_vertices(self):
        triangle = ((0., 0., 0.), (1., 0., 0.), (0., 1., 0.))
        cases = (((.2, .3, .4), (.2, .3, 0.)),
                 ((.6, .6, .2), (.5, .5, 0.)),
                 ((-.2, -.1, .2), (0., 0., 0.)),
                 ((.4, -.2, .1), (.4, 0., 0.)))
        for point, expected in cases:
            with self.subTest(point=point):
                self.assertLess(math.dist(closest_point_on_triangle(point, *triangle), expected), 1e-12)

    def test_surface_sign_and_triangle_identity_match_actual_geometry(self):
        query = SurfaceQuery(((0., 0., 0.), (.02, 0., 0.), (0., .02, 0.)), [0, 1, 2])
        above = query.nearest((.005, .005, .002), radius=.01)
        below = query.nearest((.005, .005, -.003), radius=.01)
        self.assertEqual(above["triangle_index"], 0)
        self.assertAlmostEqual(above["signed_distance"], .002)
        self.assertAlmostEqual(below["signed_distance"], -.003)
        self.assertEqual(above["normal"], [0., 0., 1.])
        self.assertIsNone(query.nearest((5., 5., 5.), radius=.01))


if __name__ == "__main__":
    unittest.main()
