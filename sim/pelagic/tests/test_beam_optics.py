import unittest

import numpy as np

from reefsim.beam_optics import add_visible_beam


class VisibleBeamTests(unittest.TestCase):
    def setUp(self):
        self.image = np.full((96, 160, 3), 40, dtype=np.uint8)
        self.depth = np.full((96, 160), 4., dtype=np.float32)
        self.options = dict(camera_world=np.eye(4), focal_length_mm=25., horizontal_aperture_mm=36.,
                            light_origin=[-.45, 0., -1.], light_direction=[1., 0., 0.],
                            half_angle_degrees=10., color_rgb=[1., 1., 1.], strength=1.,
                            visibility_m=4., max_width=80, samples=28)

    def render(self, depth=None, **options):
        return add_visible_beam(self.image, self.depth if depth is None else depth,
                                **{**self.options, **options})

    def test_off_is_exact_and_inputs_are_unchanged(self):
        original_image, original_depth = self.image.copy(), self.depth.copy()
        off = self.render(strength=0.)
        np.testing.assert_array_equal(off, self.image)
        self.assertIsNot(off, self.image)
        self.render()
        np.testing.assert_array_equal(self.image, original_image)
        np.testing.assert_array_equal(self.depth, original_depth)

    def test_light_axis_and_position_control_visible_cone(self):
        delta = self.render().astype(int) - self.image.astype(int)
        self.assertGreater(delta[48, 100, 0], 0)
        self.assertEqual(int(delta[:12].max()), 0)
        self.assertEqual(int(delta[:, :15].max()), 0)
        shifted = self.render(light_origin=[-.45, .25, -1.]).astype(int) - self.image.astype(int)
        rows = np.arange(self.image.shape[0])[:, None]
        center = float((rows*delta[..., 0]).sum() / delta[..., 0].sum())
        shifted_center = float((rows*shifted[..., 0]).sum() / shifted[..., 0].sum())
        self.assertLess(shifted_center, center - 10.)
        away = self.render(light_origin=[0., 0., 1.], light_direction=[0., 0., 1.])
        np.testing.assert_array_equal(away, self.image)

    def test_foreground_surface_clips_scattering_and_upsampling_spill(self):
        foreground = np.full_like(self.depth, .3)
        np.testing.assert_array_equal(self.render(depth=foreground), self.image)
        mixed = self.depth.copy()
        mixed[20:76, 99:101] = .3
        result = self.render(depth=mixed, max_width=32)
        np.testing.assert_array_equal(result[20:76, 99:101], self.image[20:76, 99:101])
        self.assertGreater(int(result[48, 130, 0]), 40)

    def test_usd_row_vector_world_transform_is_respected(self):
        rotation = np.array([[0., 1., 0.], [-1., 0., 0.], [0., 0., 1.]])
        translation = np.array([3., -2., 1.])
        matrix = np.eye(4)
        matrix[:3, :3] = rotation
        matrix[3, :3] = translation
        transformed = self.render(camera_world=matrix,
                                  light_origin=np.array(self.options["light_origin"]) @ rotation + translation,
                                  light_direction=np.array(self.options["light_direction"]) @ rotation)
        self.assertLessEqual(int(np.abs(transformed.astype(int)-self.render().astype(int)).max()), 1)

    def test_added_energy_is_bounded_and_only_visible_colour_is_added(self):
        result = self.render(strength=1e12, color_rgb=[1., 0., 0.])
        self.assertEqual(result.dtype, np.uint8)
        self.assertEqual(result.shape, self.image.shape)
        self.assertTrue(np.all(result >= self.image))
        np.testing.assert_array_equal(result[..., 1:], self.image[..., 1:])
        linear = lambda x: ((x.astype(np.float64)/255.+.055)/1.055)**2.4
        self.assertLessEqual(float((linear(result)-linear(self.image)).max()), .072)
        self.assertLessEqual(int(result.max()), 88)

    def test_invalid_depth_is_opaque_and_invalid_parameters_are_rejected(self):
        depth = self.depth.copy()
        depth[:, :40] = np.nan
        depth[:, 40:80] = 0.
        depth[:, 80:120] = -1.
        depth[:, 120:] = np.inf
        result = self.render(depth=depth)
        np.testing.assert_array_equal(result[:, :120], self.image[:, :120])
        self.assertTrue(np.all(np.isfinite(result)))
        for options in ({"light_direction": [0., 0., 0.]}, {"visibility_m": float("nan")},
                        {"strength": -1.}, {"color_rgb": [1., 0., float("nan")]},
                        {"samples": 4}, {"half_angle_degrees": 90.}):
            with self.subTest(options=options), self.assertRaises(ValueError):
                self.render(**options)
        with self.assertRaises(ValueError):
            add_visible_beam(self.image.astype(float), self.depth, **self.options)


if __name__ == "__main__":
    unittest.main()
