import copy
import math
import unittest
from unittest.mock import patch

from reefsim.reef_motion import generate_soft_coral, current_pose, flow_velocity


class ReefMotionTests(unittest.TestCase):
    def test_connected_seeded_mesh_contract(self):
        mesh = generate_soft_coral(26)
        self.assertEqual(mesh, generate_soft_coral(26))
        self.assertNotEqual(mesh["points"], generate_soft_coral(27)["points"])
        size = len(mesh["points"])
        self.assertGreater(size, 1000)
        self.assertLess(size, 4000)
        for key in ("normals", "colors", "uvs"):
            self.assertEqual(len(mesh[key]), size)
        self.assertEqual(sum(mesh["counts"]), len(mesh["indices"]))
        self.assertTrue(all(0 <= i < size for i in mesh["indices"]))
        self.assertTrue(all(math.isfinite(v) for key in ("points", "normals", "colors", "uvs")
                            for row in mesh[key] for v in row))

    def test_zero_current_dead_colony_and_initial_time_are_stationary(self):
        mesh = generate_soft_coral(26)
        for time, current in ((0., [.2, .1, 0.]), (18., [0., 0., 0.]), (9., [0., 0., .2])):
            self.assertEqual(current_pose(mesh, time, current)["points"], mesh["points"])
        dead = generate_soft_coral(26, health="dead")
        self.assertEqual(current_pose(dead, 20., [.3, 0., 0.])["points"], dead["points"])

    def test_current_response_is_anchored_bounded_and_history_free(self):
        mesh = generate_soft_coral(12)
        before = copy.deepcopy(mesh)
        expected = current_pose(mesh, 18.5, [.12, .03, 0.])
        for time in (4., 80., 0., 2.):
            current_pose(mesh, time, [.3, 0., 0.])
        self.assertEqual(expected, current_pose(mesh, 18.5, [.12, .03, 0.]))
        self.assertEqual(mesh, before)
        for speed in (.05, .2, 2., 100.):
            for time in (0., .05, 1., 10., 120.):
                pose = current_pose(mesh, time, [speed, .1, 0.])
                for original, point in zip(mesh["points"], pose["points"]):
                    self.assertLessEqual(math.dist(original, point), mesh["motion"]["max_displacement"] + 1e-12)
                    if original[2] <= mesh["motion"]["root_height"]:
                        self.assertEqual(original, point)
                self.assertTrue(all(abs(sum(v*v for v in n) - 1.) < 1e-6 for n in pose["normals"]))

    def test_drag_direction_strength_and_continuity(self):
        mesh = generate_soft_coral(26)
        weak = current_pose(mesh, 20., [.05, 0., 0.])["tip_displacement"]
        strong = current_pose(mesh, 20., [.25, 0., 0.])["tip_displacement"]
        reverse = current_pose(mesh, 20., [-.25, 0., 0.])["tip_displacement"]
        self.assertGreater(strong[0], weak[0])
        self.assertGreater(weak[0], 0.)
        self.assertAlmostEqual(reverse[0], -strong[0])
        self.assertAlmostEqual(reverse[1], -strong[1])
        previous = current_pose(mesh, 0., [.2, .1, 0.])["tip_displacement"]
        for step in range(1, 801):
            point = current_pose(mesh, step * .05, [.2, .1, 0.])["tip_displacement"]
            self.assertLess(math.dist(previous, point), .01)
            previous = point

    def test_invalid_inputs_are_rejected(self):
        for value in (0., -1., math.nan, math.inf):
            with self.assertRaises(ValueError):
                generate_soft_coral(26, height=value)
        mesh = generate_soft_coral(26)
        for kwargs in ({"time": math.nan}, {"time": -1}, {"current": [0, math.inf, 0]},
                       {"current": [0, 0]}, {"stiffness": 0}, {"damping": -1}, {"mass": 0},
                       {"surge_ratio": -1}, {"surge_period": 0}, {"cross_flow_ratio": 2},
                       {"phase_offset": math.inf}):
            args = {"time": 1., "current": [.1, 0., 0.]}
            args.update(kwargs)
            with self.assertRaises(ValueError):
                current_pose(mesh, **args)

    def test_foreground_fan_has_visible_cyclic_motion_and_bounded_strain(self):
        mesh = generate_soft_coral(26, height=.55, radius=.28)
        flow = [.10, .035, 0.]
        poses = [current_pose(mesh, 20. + index * .1, flow) for index in range(66)]
        tips = [pose["tip_displacement"] for pose in poses]
        excursion = max(math.dist(a, b) for a in tips for b in tips)
        self.assertGreater(excursion, .08)  # Clearly observable 8+ cm excursion.
        self.assertLessEqual(excursion, 2 * mesh["motion"]["max_displacement"])
        for pose in poses:
            self.assertLessEqual(pose["max_shear"], .30 + 1e-9)
            self.assertLessEqual(pose["max_extension_ratio"], 1.162)
        self.assertGreater(max(math.hypot(*pose["tip_velocity"]) for pose in poses), .04)
        for time in (0., 2., 5., 20.):
            self.assertEqual(flow_velocity([0., 0., 0.], time), [0., 0., 0.])
        speeds = [math.hypot(*flow_velocity(flow, index*.1)[:2]) for index in range(66)]
        self.assertGreater(max(speeds), min(speeds)*3)
        self.assertEqual(flow_velocity(flow, 1., surge_ratio=0., cross_flow_ratio=0.), flow)

    def test_motion_responds_to_stiffness_damping_and_mass(self):
        mesh = generate_soft_coral(26, height=.55, radius=.28)
        flow = [.1, .035, 0.]
        def cycle(**options):
            return [current_pose(mesh, 30. + index*.1, flow, **options)["tip_displacement"]
                    for index in range(66)]
        flexible, stiff = cycle(stiffness=.4), cycle(stiffness=4.)
        self.assertGreater(max(math.hypot(*p) for p in flexible),
                           max(math.hypot(*p) for p in stiff) * 1.4)
        def excursion(points):
            return max(math.dist(a,b) for a in points for b in points)
        self.assertGreater(excursion(cycle(damping=.2)), excursion(cycle(damping=2.4)))
        light = current_pose(mesh, .25, flow, mass=.01)["tip_displacement"]
        heavy = current_pose(mesh, .25, flow, mass=.2)["tip_displacement"]
        self.assertGreater(math.hypot(*light), math.hypot(*heavy))

    def test_optional_acceleration_preserves_output_and_stdlib_fallback(self):
        def assert_same_pose(expected, actual):
            self.assertEqual(expected.keys(), actual.keys())
            self.assertEqual({k:v for k,v in expected.items() if k not in ('points','normals')},
                             {k:v for k,v in actual.items() if k not in ('points','normals')})
            for key in ('points','normals'):
                self.assertEqual(type(expected[key]), type(actual[key]))
                self.assertEqual(len(expected[key]), len(actual[key]))
                for left,right in zip(expected[key],actual[key]):
                    self.assertEqual(type(left),type(right))
                    self.assertEqual(len(left),len(right))
                    self.assertEqual(len(left),3)
                    self.assertTrue(all(math.isfinite(v) for v in (*left,*right)))
                    # Scalar and SIMD normalization can differ by a few ULPs
                    # across ARM/x86; 1e-12 is far below USD float precision.
                    self.assertLessEqual(max(abs(a-b) for a,b in zip(left,right)),1e-12)
        mesh=generate_soft_coral(26,height=.55,radius=.28)
        before=copy.deepcopy(mesh)
        for time,flow in ((0.,[.1,.035,0.]),(20.5,[.1,.035,0.]),
                          (11.,[0.,0.,0.]),(30.,[-.2,.1,0.])):
            slow=current_pose(mesh,time,flow,accelerated=False)
            fast=current_pose(mesh,time,flow,accelerated=True)
            assert_same_pose(slow,fast)
            with patch('reefsim.reef_motion._np',None):
                self.assertEqual(slow,current_pose(mesh,time,flow))
        self.assertEqual(mesh,before)
        # Rest geometry remains an ordinary mutable dict: no cached arrays
        # may silently ignore edits supplied before a subsequent evaluation.
        mesh['points'][100]=tuple(v+.001 for v in mesh['points'][100])
        assert_same_pose(current_pose(mesh,20.,[.1,.035,0.],accelerated=False),
                         current_pose(mesh,20.,[.1,.035,0.],accelerated=True))
        mesh['points'][100]=list(mesh['points'][100])
        current_pose(mesh,20.,[.1,.035,0.],accelerated=True)
        mesh['points'][100][0]+=.001
        mesh['motion']['root_height']+=.001
        assert_same_pose(current_pose(mesh,20.,[.1,.035,0.],accelerated=False),
                         current_pose(mesh,20.,[.1,.035,0.],accelerated=True))


if __name__ == "__main__":
    unittest.main()
