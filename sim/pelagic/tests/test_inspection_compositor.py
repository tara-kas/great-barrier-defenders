import unittest

from PIL import Image

from reefsim.inspection import appearance_profile
from reefsim.inspection_compositor import compose_inspection, WHITE_BOX, ACTIVE_BOX, ROBOT_BOX
from scripts.render_inspection import select_cases, mode_frame_counts


class InspectionCompositorTests(unittest.TestCase):
    def test_real_camera_inputs_stay_distinct_in_comparison(self):
        profile = appearance_profile("coral-test", group="pink")
        case = {"coral_id": "coral-test", "health": "bleached_alive", "profile": profile}
        white = Image.new("RGB", (960, 540), (220, 100, 30))
        active = Image.new("RGB", (960, 540), (190, 20, 120))
        robot = Image.new("RGB", (640, 360), (30, 100, 180))
        result = compose_inspection(white, active, robot, case, {"mode": "uv"})
        self.assertEqual(result.size, (1600, 900))
        for box, color in ((WHITE_BOX, (220, 100, 30)), (ACTIVE_BOX, (190, 20, 120)),
                           (ROBOT_BOX, (30, 100, 180))):
            self.assertEqual(result.getpixel(((box[0]+box[2])//2, (box[1]+box[3])//2)), color)

    def test_every_health_and_group_has_a_real_existing_case(self):
        from reefsim.core import ReefSimulation
        from reefsim.inspection import GROUPS
        corals = ReefSimulation().snapshot()["corals"]
        profiles = {coral["id"]: appearance_profile(coral["id"], group=GROUPS[i % 5])
                    for i, coral in enumerate(corals)}
        cases = select_cases(corals, profiles)
        self.assertEqual(len(cases), 15)
        self.assertEqual(len({case["coral_id"] for case in cases}), 15)
        self.assertEqual(sum(mode_frame_counts(24).values()) * len(cases), 1080)
        for health in ("healthy", "bleached_alive", "dead"):
            self.assertEqual({c["profile"]["group"] for c in cases if c["health"] == health}, set(GROUPS))
        with self.assertRaises(ValueError):
            select_cases(corals[:6], profiles)


if __name__ == "__main__":
    unittest.main()
