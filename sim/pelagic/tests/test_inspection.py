import copy
import math
import unittest

from reefsim.inspection import (GROUPS, HEALTH_STATES, appearance_profile,
                                beam_exposure, inspection_response, showcase_profiles,
                                auto_inspection_mode, beam_footprint_radius)


class InspectionTests(unittest.TestCase):
    def test_auto_light_policy_covers_all_mission_phases_and_carrying_override(self):
        scan_phases = {"NAVIGATE_TO_SCAN_RECIPIENT", "SCAN_RECIPIENT",
                       "NAVIGATE_TO_DONOR", "SCAN_DONOR"}
        white_phases = {"PLAN", "WAIT_FOR_MAP", "NAVIGATE_TO_PICKUP", "DETECTION_REJECTED", "APPROACH_FRAGMENT", "CLOSE_GRIPPER",
                        "DETACH_FRAGMENT", "RETRACT_FRAGMENT", "NAVIGATE_TO_SITE",
                        "LOWER_FRAGMENT", "SECURE_FRAGMENT", "OPEN_GRIPPER",
                        "RETRACT_GRIPPER", "VERIFY_ATTACHMENT", "NO_COMPATIBLE_DONOR",
                        "NO_STOCK", "COMPLETE", "SURVEY", "SURVEY_COMPLETE",
                        "PAUSED", "HOLD", "IDLE", "FAILED", "INSPECTION_CASE"}
        for phase in scan_phases | white_phases:
            with self.subTest(phase=phase):
                self.assertEqual(auto_inspection_mode(phase),
                                 "uv" if phase in scan_phases else "white")
                self.assertEqual(auto_inspection_mode(phase, carrying=True), "white")
                self.assertEqual(auto_inspection_mode(phase, carrying="fragment-001"), "white")
        # Future states fail closed, rather than inheriting a previous UV mode.
        for phase in ("FUTURE_UNKNOWN_PHASE", "", None, 17):
            self.assertEqual(auto_inspection_mode(phase), "white")

    def test_beam_footprint_matches_cone_geometry_and_wide_scan_configuration(self):
        self.assertEqual(beam_footprint_radius(0.,50.),0.)
        self.assertAlmostEqual(beam_footprint_radius(1.,45.),1.)
        radius=beam_footprint_radius(1.1,50.)
        self.assertAlmostEqual(radius,1.31092895185,places=10)
        self.assertGreater(radius,beam_footprint_radius(1.1,24.)*2.5)
        self.assertAlmostEqual(beam_footprint_radius(2.2,50.),radius*2)
        light=lambda point:beam_exposure(point,(0.,0.,0.),(0.,0.,1.),
                                         range_m=3.5,half_angle_degrees=50.,attenuation=0.)
        self.assertGreater(light((radius*.5,0.,1.1)),0.)
        self.assertEqual(light((radius*1.001,0.,1.1)),0.)
        for distance,angle in ((-1.,50.),(math.nan,50.),(math.inf,50.),(True,50.),
                               (1.,0.),(1.,90.),(1.,-5.),(1.,math.nan),(1.,False),
                               (1e308,89.)):
            with self.subTest(distance=distance,angle=angle):
                with self.assertRaises(ValueError):
                    beam_footprint_radius(distance,angle)

    def test_profiles_are_deterministic_independent_and_preserve_donor_identity(self):
        donor = appearance_profile("coral-003", 26)
        fragment = {"id": "fragment-003", "donor_id": "coral-003"}
        self.assertEqual(donor, appearance_profile(fragment["donor_id"], 26))
        modified = appearance_profile("coral-003", 26)
        modified["pigment_rgb"][0] = 999
        self.assertEqual(donor, appearance_profile("coral-003", 26))
        profiles = [appearance_profile(f"coral-{i:03d}", 26) for i in range(100)]
        self.assertEqual({p["group"] for p in profiles}, set(GROUPS))
        # A colour must not be a unique genotype lookup in this demonstration.
        self.assertTrue(any(len({p["synthetic_genotype"] for p in profiles if p["group"] == group}) > 1
                            for group in GROUPS))

    def test_beam_is_local_directional_smooth_and_attenuated(self):
        def exposure(point, **kwargs):
            return beam_exposure(point, (0., 0., 0.), (0., 0., -4.), **kwargs)
        self.assertEqual(exposure((0., 0., 1.)), 0.)
        self.assertEqual(exposure((2., 0., -1.)), 0.)
        self.assertEqual(exposure((0., 0., -2.5)), 0.)
        self.assertEqual(exposure((0., 0., 0.)), 1.)
        self.assertGreater(exposure((0., 0., -.5)), exposure((0., 0., -1.)))
        self.assertGreater(exposure((0., 0., -1.), attenuation=0), exposure((0., 0., -1.)))
        self.assertAlmostEqual(exposure((0., 0., -1.)),
                               beam_exposure((0, 0, -1), (0, 0, 0), (0, 0, -1e300)))
        outer = math.tan(math.radians(28.))
        self.assertLess(exposure((outer - 1e-5, 0., -1.)), 1e-7)
        for distance in (.01, .2, 1., 2.49999):
            value = exposure((0., 0., -distance))
            self.assertTrue(math.isfinite(value))
            self.assertGreaterEqual(value, 0.)
            self.assertLessEqual(value, 1.)

    def test_complete_showcase_keeps_health_separate_from_signal(self):
        cases = showcase_profiles()
        self.assertEqual(len(cases), 15)
        self.assertEqual(len({case["id"] for case in cases}), 15)
        self.assertEqual({(case["health"], case["profile"]["group"]) for case in cases},
                         {(health, group) for health in HEALTH_STATES for group in GROUPS})
        before = copy.deepcopy(cases)
        for case in cases:
            for mode in ("off", "white", "blue", "uv"):
                response = inspection_response(case["profile"], case["health"], .8, mode)
                self.assertEqual(response["health"], case["health"])
                self.assertFalse(response["health_inferred_from_signal"])
                self.assertEqual(response["eligible_recipient"], case["health"] == "bleached_alive")
                self.assertTrue(all(math.isfinite(v) and 0 <= v <= 1 for v in response["emission_rgb"]))
                if mode in ("off", "white") or case["health"] == "dead" or case["profile"]["negative_control"]:
                    self.assertEqual(response["emission_rgb"], [0., 0., 0.])
            self.assertEqual(inspection_response(case["profile"], case["health"], 0., "blue")["emission_rgb"], [0., 0., 0.])
        self.assertEqual(cases, before)
        profile = appearance_profile("test", group="yellow")
        healthy = inspection_response(profile, "healthy", 1., "blue")
        bleached = inspection_response(profile, "bleached_alive", 1., "blue")
        self.assertGreater(sum(bleached["emission_rgb"]), sum(healthy["emission_rgb"]))

    def test_invalid_inputs_fail_before_rendering(self):
        profile = appearance_profile("test")
        for exposure in (math.nan, math.inf, -1., 1.001, True):
            with self.assertRaises(ValueError):
                inspection_response(profile, "healthy", exposure)
        for args in ({"range_m": 0}, {"half_angle_degrees": 90}, {"attenuation": -1}):
            with self.assertRaises(ValueError):
                beam_exposure((0, 0, -1), (0, 0, 0), (0, 0, -1), **args)
        with self.assertRaises(ValueError):
            beam_exposure((0, 0, -1), (0, 0, 0), (0, 0, 0))
        with self.assertRaises(ValueError):
            appearance_profile("test", group="genotype-from-colour")
        with self.assertRaises(ValueError):
            inspection_response(profile, "revived_dead", 1., "blue")


if __name__ == "__main__":
    unittest.main()
