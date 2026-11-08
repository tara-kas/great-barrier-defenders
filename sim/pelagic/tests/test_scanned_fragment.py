import math
import unittest

from reefsim.pocillopora_scan import generate_pocillopora_scan
from reefsim.scanned_fragment import split_scanned_donor, _topology


class ScannedFragmentTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = generate_pocillopora_scan("healthy", .35, .35, 44, detail="hero")
        cls.split = split_scanned_donor(.35, .35, 44, detail="hero")

    def test_original_surface_is_partitioned_without_duplicate_or_missing_faces(self):
        pieces = [self.split["parent"]] + [f["mesh"] for f in self.split["fragments"]]
        all_ids = [i for mesh in pieces for i in mesh["source_triangle_indices"]]
        self.assertEqual(len(all_ids), len(set(all_ids)))
        self.assertEqual(sorted(all_ids), list(range(self.split["source_triangle_count"])))

    def test_exact_initial_reconstruction_preserves_uvs_normals_and_colors(self):
        pieces = [(self.split["parent"], (0., 0., 0.))]
        pieces += [(f["mesh"], f["origin"]) for f in self.split["fragments"]]
        for mesh, origin in pieces:
            for new_id, source_id in enumerate(mesh["source_vertex_indices"]):
                for k in range(3):
                    self.assertAlmostEqual(mesh["points"][new_id][k] + origin[k],
                                           self.source["points"][source_id][k], places=12)
                for attribute in ("uvs", "normals", "colors"):
                    self.assertEqual(mesh[attribute][new_id], self.source[attribute][source_id])
            for new_face, source_face in enumerate(mesh["source_triangle_indices"]):
                actual = [mesh["source_vertex_indices"][v] for v in mesh["indices"][new_face*3:new_face*3+3]]
                self.assertEqual(actual, self.source["indices"][source_face*3:source_face*3+3])

    def test_each_cutting_is_one_connected_piece_of_actual_tissue(self):
        _, _, neighbours, _, _ = _topology("hero")
        for fragment in self.split["fragments"]:
            unseen = set(fragment["source_triangle_indices"])
            pending = [unseen.pop()]
            while pending:
                for other in neighbours[pending.pop()]:
                    if other in unseen:
                        unseen.remove(other)
                        pending.append(other)
            self.assertFalse(unseen)

    def test_measured_grasp_and_bounds_fit_real_geometry(self):
        for fragment in self.split["fragments"]:
            mesh = fragment["mesh"]
            self.assertGreater(fragment["height"], .05)
            self.assertLess(fragment["height"], .10)
            self.assertEqual(min(p[2] for p in mesh["points"]), 0.)
            self.assertAlmostEqual(max(p[2] for p in mesh["points"]), fragment["height"])
            self.assertEqual(fragment["yaw"], 0.)
            self.assertGreater(fragment["cap_triangle_count"], 0)
            low, high = fragment["contact_band_local_z"]
            self.assertLess(low, fragment["grasp_z"])
            self.assertGreater(high, fragment["grasp_z"])
            self.assertGreater(len(fragment["contact_samples"]), 10)
            for p in fragment["contact_samples"]:
                self.assertTrue(low - 1e-12 <= p[2] <= high + 1e-12)
                self.assertLessEqual(math.hypot(*p[:2]), fragment["grasp_radius"] + 1e-12)
            self.assertLessEqual(fragment["grasp_radius"], fragment["radius"])

    def test_caps_are_opposite_matched_surfaces_and_all_buffers_valid(self):
        parent = self.split["parent"]
        parent_cap_start = parent["source_triangle_count"] * 3
        parent_caps = {}
        for i in range(parent_cap_start, len(parent["indices"]), 3):
            ids = parent["indices"][i:i+3]
            key = tuple(sorted(tuple(round(x, 10) for x in parent["points"][j]) for j in ids))
            parent_caps[key] = parent["normals"][ids[0]]
        for fragment in self.split["fragments"]:
            mesh, origin = fragment["mesh"], fragment["origin"]
            for i in range(mesh["source_triangle_count"]*3, len(mesh["indices"]), 3):
                ids = mesh["indices"][i:i+3]
                key = tuple(sorted(tuple(round(mesh["points"][j][k]+origin[k], 10) for k in range(3)) for j in ids))
                self.assertIn(key, parent_caps)
                self.assertAlmostEqual(sum(a*b for a, b in zip(mesh["normals"][ids[0]], parent_caps[key])), -1.)
        for mesh in [parent] + [f["mesh"] for f in self.split["fragments"]]:
            for key in ("normals", "colors", "uvs"):
                self.assertEqual(len(mesh[key]), len(mesh["points"]))
            self.assertEqual(sum(mesh["counts"]), len(mesh["indices"]))
            self.assertTrue(all(0 <= v < len(mesh["points"]) for v in mesh["indices"]))
            self.assertTrue(all(math.isfinite(x) for key in ("points", "normals", "colors", "uvs") for row in mesh[key] for x in row))

    def test_deterministic_independent_output_and_optional_single_fragment(self):
        a = split_scanned_donor(.35, .35, 44, slots=1, detail="standard")
        b = split_scanned_donor(.35, .35, 44, slots=1, detail="standard")
        self.assertEqual(a, b)
        a["fragments"][0]["mesh"]["points"][0] = (99., 99., 99.)
        self.assertNotEqual(a, b)
        source_ids = b["parent"]["source_triangle_indices"] + b["fragments"][0]["source_triangle_indices"]
        self.assertEqual(sorted(source_ids), list(range(b["source_triangle_count"])))
        intact = split_scanned_donor(.35, .35, slots=0, detail="standard")
        self.assertEqual(intact["fragments"], [])
        self.assertEqual(intact["parent"]["source_triangle_count"], intact["source_triangle_count"])

    def test_invalid_requests_fail_explicitly(self):
        for slots in (-1, 3, True, .5):
            with self.assertRaises(ValueError):
                split_scanned_donor(.35, .35, slots=slots)
        for radius, height in ((0, .3), (.3, float("nan")), (-.1, .3)):
            with self.assertRaises(ValueError):
                split_scanned_donor(radius, height)


if __name__ == "__main__":
    unittest.main()
