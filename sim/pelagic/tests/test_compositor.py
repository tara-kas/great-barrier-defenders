import copy
import unittest

import numpy as np
from PIL import Image

from reefsim.compositor import compose_frame, phase_name, inspection_caption, MAIN_BOX, SCOUT_BOX, WORKER_BOX
from scripts.render_demo import build_schedule
from scripts.validate_demo import validate_detection_recording, MANIPULATION_STATES


class CompositorTests(unittest.TestCase):
    def test_detection_and_mechanical_check_captions_have_distinct_purposes(self):
        for phase, target in (("SCAN_RECIPIENT", "RECIPIENT"), ("SCAN_DONOR", "DONOR")):
            title, description = phase_name({"robots": [{"role": "restoration", "state": phase}]})
            self.assertIn("UV DETECTION", title)
            self.assertIn("before", description)
            title, explanation = inspection_caption({"mode": "uv", "visible_uv_pilot": True}, phase)
            self.assertIn(target, title)
            self.assertIn("UV INVISIBLE", explanation)
            self.assertIn("VIOLET AIM LIGHT", explanation)
        for contact in (False, True):
            state = {"robots": [{"role": "restoration", "state": "VERIFY_ATTACHMENT"}],
                     "corals": [{"contact_fixture": {"kind": "natural_branch"}}] if contact else []}
            title, description = phase_name(state)
            self.assertIn("MECHANICAL CHECK", title)
            self.assertIn("White-light", description)
            self.assertNotIn("UV", title + description)
        self.assertEqual(inspection_caption({"mode": "white"}, "CLOSE_GRIPPER")[0], "WHITE / MANIPULATION")
        self.assertEqual(inspection_caption({"mode": "white"}, "NAVIGATE_TO_PICKUP")[0], "WHITE / MANIPULATION")
        self.assertIn("UV checks accepted", phase_name({"robots": [{"role": "restoration", "state": "NAVIGATE_TO_PICKUP"}]})[1])
        provisional = {"detection_required": True, "corals": [{"contact_fixture": {"kind": "natural_branch"}}],
                       "robots": [{"role": "restoration", "state": "PLAN"}]}
        self.assertIn("provisional", phase_name(provisional)[1])
        self.assertIn("before harvest", phase_name(provisional)[1])
        provisional["robots"][0]["state"] = "DETECTION_REJECTED"
        self.assertIn("no harvesting", phase_name(provisional)[1])

    def test_recording_rejects_uv_after_detection_or_during_carry(self):
        state = {"recording": {"inspection_config": {"enabled": True}}}
        valid = [{"worker_state": "NAVIGATE_TO_DONOR", "inspection": {"mode": "uv"}},
                 {"worker_state": "VERIFY_ATTACHMENT", "inspection": {"mode": "white"}}]
        self.assertFalse(validate_detection_recording(state, valid)["required"])
        for phase in MANIPULATION_STATES:
            with self.subTest(phase=phase), self.assertRaisesRegex(AssertionError, "must use white"):
                validate_detection_recording(state, valid + [{"worker_state": phase, "inspection": {"mode": "uv"}}])
        with self.assertRaisesRegex(AssertionError, "must use white"):
            validate_detection_recording(state, valid + [{"worker_state": "NAVIGATE_TO_DONOR", "carrying": True,
                                                         "inspection": {"mode": "uv"}}])
        with self.assertRaisesRegex(AssertionError, "before harvest"):
            validate_detection_recording(state, valid + [{"worker_state": "COMPLETE", "inspection": {"mode": "uv"}}])

    def test_detection_receipts_must_precede_each_fragments_manipulation(self):
        recipient = {"coral_id": "recipient-1", "role": "recipient", "timestamp": 2., "mode": "uv",
                     "accepted": True, "fragment_id": "frag-1", "paired_colony_id": "donor-1"}
        donor = dict(recipient, coral_id="donor-1", role="donor", paired_colony_id="recipient-1", timestamp=4.)
        state = {"recording": {"inspection_config": {"enabled": True, "require_detection": True}},
                 "detection_required": True, "detection_history": [recipient, donor],
                 "fragments": [{"id": "frag-1", "donor_id": "donor-1", "target_id": "recipient-1", "stage": "placed",
                                "detection_approved_at": 4., "harvested_at": 7.,
                                "detection_evidence": {"recipient": recipient, "donor": donor}}]}
        manifest = [{"worker_state": phase, "sim_time": t, "fragment_id": "frag-1", "inspection": {"mode": mode}}
                    for phase, t, mode in (("SCAN_RECIPIENT", 1., "uv"), ("SCAN_DONOR", 3., "uv"), ("NAVIGATE_TO_PICKUP", 4.1, "white"),
                                           ("CLOSE_GRIPPER", 6., "white"), ("VERIFY_ATTACHMENT", 20., "white"))]
        self.assertEqual(validate_detection_recording(state, manifest)["approved_fragments"], ["frag-1"])
        mutations = [
            lambda s: s["fragments"][0]["detection_evidence"].pop("donor"),
            lambda s: s["fragments"][0].update(harvested_at=3.),
            lambda s: s["detection_history"][1].update(accepted=False),
            lambda s: s["detection_history"][1].update(fragment_id="other"),
            lambda s: s["detection_history"][1].update(paired_colony_id="wrong-target"),
            lambda s: s["detection_history"].clear(),
        ]
        for mutate in mutations:
            bad = copy.deepcopy(state)
            mutate(bad)
            with self.assertRaises(AssertionError):
                validate_detection_recording(bad, manifest)
        with self.assertRaisesRegex(AssertionError, "before UV approval"):
            validate_detection_recording(state, manifest + [{"worker_state": "CLOSE_GRIPPER", "sim_time": 2.5,
                                                             "fragment_id": "frag-1", "inspection": {"mode": "white"}}])
        with self.assertRaisesRegex(AssertionError, "omitted"):
            validate_detection_recording(state, [e for e in manifest if e["worker_state"] != "SCAN_RECIPIENT"])
        with self.assertRaisesRegex(AssertionError, "omitted this fragment"):
            validate_detection_recording(state, [dict(e, fragment_id="other") if e["worker_state"] == "SCAN_DONOR" else e
                                                 for e in manifest])

    def test_each_camera_remains_distinct_and_uncropped(self):
        main = np.full((720, 1280, 3), (190, 30, 20), dtype=np.uint8)
        scout = np.full((240, 400, 3), (20, 180, 30), dtype=np.uint8)
        worker = np.full((240, 400, 3), (20, 30, 180), dtype=np.uint8)
        state = {"time": 32., "water": {"visibility": 3.8, "current": [.1, 0, 0]},
                 "robots": [{"role": "survey", "state": "SURVEY"},
                            {"role": "restoration", "state": "CLOSE_GRIPPER"}],
                 "metrics": {"observed": 12, "total_corals": 24, "verified": 0, "donor_fragments_available": 6}}
        result = compose_frame(main, scout, worker, state)
        self.assertEqual(result.size, (1600, 900))
        for box, expected in ((MAIN_BOX, (190, 30, 20)), (SCOUT_BOX, (20, 180, 30)), (WORKER_BOX, (20, 30, 180))):
            point = ((box[0] + box[2]) // 2, (box[1] + box[3]) // 2)
            self.assertEqual(result.getpixel(point), expected)

    def test_schedule_preserves_full_mission_and_action_milestones(self):
        schedule = build_schedule(None, fps=24, max_frames=2000)
        self.assertLessEqual(len(schedule["ticks"]), 2000)
        self.assertEqual(schedule["ticks"][0], 0)
        self.assertTrue(all(a <= b for a, b in zip(schedule["ticks"], schedule["ticks"][1:])))
        self.assertEqual(schedule["ticks"][-1], schedule["milestones"]["complete"])
        self.assertEqual(schedule["final_metrics"]["verified"], 4)
        self.assertTrue(schedule["final_metrics"]["mission_complete"])
        self.assertEqual(set(schedule["milestones"]), {"survey", "donor_approach", "closed_grasp", "detachment", "carrying", "placement", "release", "retreat", "verification", "complete"})
        self.assertGreaterEqual(schedule["first_carry_video_seconds"], 2.)
        self.assertTrue({"APPROACH_FRAGMENT", "CLOSE_GRIPPER", "DETACH_FRAGMENT", "RETRACT_FRAGMENT", "LOWER_FRAGMENT", "SECURE_FRAGMENT", "OPEN_GRIPPER", "RETRACT_GRIPPER", "VERIFY_ATTACHMENT"} <= set(schedule["action_states_seen"]))
        self.assertGreater(schedule["duration_seconds"], 45)
        self.assertLessEqual(schedule["duration_seconds"], 2000 / 24)


if __name__ == "__main__":
    unittest.main()
