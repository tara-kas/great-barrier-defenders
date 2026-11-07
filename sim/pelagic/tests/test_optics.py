import unittest
import numpy as np
from reefsim.optics import underwater_image, png_bytes


class OpticsTests(unittest.TestCase):
    def test_distance_removes_red_and_preserves_nearby_detail(self):
        rgb = np.full((20, 20, 3), 220, dtype=np.uint8)
        near = underwater_image(rgb, np.zeros((20, 20)), seed=4)
        far = underwater_image(rgb, np.full((20, 20), 5.), seed=4)
        self.assertGreater(near.mean(), far.mean())
        self.assertLess(far[..., 0].mean(), far[..., 2].mean())

    def test_bad_depth_is_finite_and_output_is_png(self):
        image = underwater_image(np.full((2, 2, 4), 255, dtype=np.uint8),
                                 np.array([[float("nan"), float("inf")], [-1, 2]]))
        self.assertEqual(image.shape, (2, 2, 3))
        self.assertTrue(png_bytes(image).startswith(b"\x89PNG\r\n\x1a\n"))

    def test_visibility_and_seed_have_real_effects(self):
        rgb = np.full((20, 20, 3), 180, dtype=np.uint8)
        depth = np.full((20, 20), 3.)
        clear = underwater_image(rgb, depth, 8., seed=42)
        murky = underwater_image(rgb, depth, 1., seed=42)
        self.assertFalse(np.array_equal(clear, murky))
        np.testing.assert_array_equal(clear, underwater_image(rgb, depth, 8., seed=42))

    def test_shape_mismatch_rejected(self):
        with self.assertRaises(ValueError):
            underwater_image(np.zeros((3, 3, 3)), np.zeros((2, 2)))


if __name__ == "__main__":
    unittest.main()
