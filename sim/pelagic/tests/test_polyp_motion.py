import copy
import math
import unittest
from unittest.mock import patch

from reefsim.polyp_motion import generate_polyp_patch, polyp_current_pose


class PolypMotionTests(unittest.TestCase):
    anchors = [
        {"point": [.02,.03,.20], "normal": [0.,0.,1.], "color": [.7,.5,.3]},
        {"point": [-.03,.02,.18], "normal": [.5,0.,.866], "color": [.7,.65,.55]},
    ]

    def test_patch_is_seeded_attached_finite_and_dead_has_no_living_tissue(self):
        mesh = generate_polyp_patch(self.anchors, health="bleached_alive")
        self.assertEqual(mesh, generate_polyp_patch(self.anchors, health="bleached_alive"))
        size = len(mesh["points"])
        self.assertGreater(size,500)
        self.assertLess(size,1000)
        self.assertEqual(sum(mesh["counts"]), len(mesh["indices"]))
        for key in ("normals","colors","uvs"):
            self.assertEqual(size,len(mesh[key]))
        for key in ("owners","weights","slopes"):
            self.assertEqual(size,len(mesh["motion"][key]))
        self.assertTrue(all(0<=i<size for i in mesh["indices"]))
        self.assertTrue(all(math.isfinite(v) for key in ("points","normals","colors","uvs")
                            for row in mesh[key] for v in row))
        dead=generate_polyp_patch(self.anchors,health="dead")
        self.assertEqual(dead["points"],[])
        self.assertEqual(polyp_current_pose(dead,10.,[.1,0.,0.])["polyp_count"],0)

    def test_current_moves_only_tentacles_with_fixed_roots_and_bounded_strain(self):
        mesh=generate_polyp_patch(self.anchors)
        original=copy.deepcopy(mesh)
        self.assertEqual(polyp_current_pose(mesh,10.,[0.,0.,0.])["points"],mesh["points"])
        self.assertEqual(polyp_current_pose(mesh,0.,[.1,0.,0.])["points"],mesh["points"])
        pose=polyp_current_pose(mesh,21.,[.1,.035,0.])
        self.assertGreater(pose["max_displacement"],.0002)
        self.assertLess(pose["max_displacement"],.002)
        self.assertLessEqual(pose["max_shear"],.405+1e-9)
        self.assertLessEqual(pose["max_extension_ratio"],1.223)
        for before,after,owner,weight in zip(mesh["points"],pose["points"],
                mesh["motion"]["owners"],mesh["motion"]["weights"]):
            if owner<0 or weight==0:
                self.assertEqual(before,after)
        self.assertTrue(all(abs(math.hypot(*n)-1)<1e-6 for n in pose["normals"]))
        self.assertEqual(mesh,original)
        polyp_current_pose(mesh,200.,[20.,10.,0.])
        self.assertEqual(pose,polyp_current_pose(mesh,21.,[.1,.035,0.]))

    def test_stiffness_and_flow_change_tissue_motion(self):
        mesh=generate_polyp_patch(self.anchors)
        soft=polyp_current_pose(mesh,21.,[.1,.035,0.],stiffness=.025)
        stiff=polyp_current_pose(mesh,21.,[.1,.035,0.],stiffness=.2)
        self.assertGreater(soft["max_displacement"],stiff["max_displacement"])
        early=polyp_current_pose(mesh,20.,[.1,.035,0.])
        later=polyp_current_pose(mesh,23.,[.1,.035,0.])
        self.assertNotEqual(early["points"],later["points"])

    def test_invalid_inputs(self):
        for kwargs in ({"health":"unknown"},{"tentacle_length":0.},{"tentacle_length":math.nan},
                       {"tentacles":8},{"seed":True}):
            with self.assertRaises(ValueError):generate_polyp_patch(self.anchors,**kwargs)
        with self.assertRaises(ValueError):
            generate_polyp_patch([{"point":[0.,0.,0.],"normal":[0.,0.,0.]}])
        mesh=generate_polyp_patch(self.anchors)
        for time,current in ((-1.,[0.,0.,0.]),(math.inf,[0.,0.,0.]),(1.,[0.,math.nan,0.])):
            with self.assertRaises(ValueError):polyp_current_pose(mesh,time,current)

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
        for health in ('healthy','bleached_alive','dead'):
            mesh=generate_polyp_patch(self.anchors,health=health)
            original=copy.deepcopy(mesh)
            for time,flow in ((0.,[.1,.035,0.]),(20.5,[.1,.035,0.]),
                              (11.,[0.,0.,0.]),(30.,[-.2,.1,.03])):
                slow=polyp_current_pose(mesh,time,flow,accelerated=False)
                assert_same_pose(slow,polyp_current_pose(mesh,time,flow,accelerated=True))
                with patch('reefsim.polyp_motion._np',None):
                    self.assertEqual(slow,polyp_current_pose(mesh,time,flow))
            self.assertEqual(mesh,original)
        mesh=generate_polyp_patch(self.anchors)
        polyp_current_pose(mesh,20.,[.1,.035,0.],accelerated=True)
        active=next(i for i,value in enumerate(mesh['motion']['weights']) if value>.1)
        mesh['points'][active]=list(mesh['points'][active])
        polyp_current_pose(mesh,20.,[.1,.035,0.],accelerated=True)
        mesh['points'][active][0]+=.001
        mesh['motion']['weights'][active]*=.5
        assert_same_pose(polyp_current_pose(mesh,20.,[.1,.035,0.],accelerated=False),
                         polyp_current_pose(mesh,20.,[.1,.035,0.],accelerated=True))


if __name__ == '__main__':
    unittest.main()
