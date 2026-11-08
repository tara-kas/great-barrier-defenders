import math
import unittest

from reefsim.core import ReefSimulation
from reefsim.pocillopora_scan import generate_pocillopora_scan
from reefsim.scanned_fragment import split_scanned_donor


class NaturalCuttingCoreTests(unittest.TestCase):
    def test_opt_in_fragments_reconstruct_donor_with_stable_slot_and_pose(self):
        sim = ReefSimulation({"render": {"natural_cuttings": True, "realistic_tissue": True},
                              "donors": {"max_fragments": 3}})
        self.assertEqual(len(sim.fragments), 3)
        for fragment in sim.fragments:
            donor = sim._truth_by_id[fragment["donor_id"]]
            self.assertTrue(donor["scanned_partition"])
            self.assertTrue(fragment["natural_cutting"])
            self.assertEqual(fragment["yaw"], 0.)
            self.assertEqual(fragment["source_mesh_seed"], sim.config["seed"] + sim.corals.index(donor)*813)
            self.assertEqual(fragment["source_mesh_detail"], "hero")
            split = split_scanned_donor(donor["radius"], donor["height"], fragment["source_mesh_seed"],
                                       slots=donor["scanned_partition_slots"], detail="hero")
            part = split["fragments"][fragment["source_slot"]]
            source = generate_pocillopora_scan("healthy", donor["radius"], donor["height"],
                                              fragment["source_mesh_seed"], detail="hero")
            self.assertEqual(fragment["source_position"], fragment["base_world"])
            self.assertEqual(fragment["position"], fragment["base_world"])
            self.assertEqual(fragment["height"], part["height"])
            self.assertEqual(fragment["grasp_radius"], part["grasp_radius"])
            for local_id, source_id in enumerate(part["mesh"]["source_vertex_indices"]):
                for k in range(3):
                    self.assertAlmostEqual(part["mesh"]["points"][local_id][k]+fragment["base_world"][k],
                                           source["points"][source_id][k]+donor["position"][k], places=12)
        self.assertEqual([c["scanned_partition_slots"] for c in sim.corals if c.get("scanned_partition")], [2, 1])

    def test_detach_preserves_pose_and_carry_rotates_local_grasp_offset(self):
        sim = ReefSimulation({"render": {"natural_cuttings": True}, "donors": {"max_fragments": 1}})
        fragment, robot = sim.fragments[0], sim.robots[1]
        source = fragment["source_position"][:]
        robot.update(fragment_id=fragment["id"], state="DETACH_FRAGMENT", carrying=True, yaw=.63)
        robot["gripper_world"] = sim._fragment_grasp(fragment, source, fragment["yaw"])
        fragment.update(stage="carried", _grasp_yaw_offset=-robot["yaw"])
        sim._sync_attachments()
        for actual, expected in zip(fragment["base_world"], source):
            self.assertAlmostEqual(actual, expected, places=12)
        # A non-central grip is supported, rather than an accidental special
        # case of all current scan chunks being centered at x=y=0.
        fragment["grasp_point"] = [.012, -.008, fragment["grasp_z"]]
        robot.update(yaw=1.1, gripper_world=[1., 2., .7])
        sim._sync_attachments()
        reconstructed = sim._fragment_grasp(fragment, fragment["base_world"], fragment["yaw"])
        for actual, expected in zip(reconstructed, robot["gripper_world"]):
            self.assertAlmostEqual(actual, expected, places=12)

    def test_default_geometry_and_grip_remain_legacy(self):
        sim = ReefSimulation()
        self.assertTrue(all(not c.get("scanned_partition") for c in sim.corals))
        self.assertTrue(all(not f.get("natural_cutting") for f in sim.fragments))
        self.assertEqual(sim.fragments[0]["height"], .14)
        self.assertEqual(sim._fragment_grasp(sim.fragments[0], [1., 2., 3.], math.pi/3), [1., 2., 3.045])


if __name__ == "__main__":
    unittest.main()
