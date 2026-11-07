import hashlib
import json
import math
from pathlib import Path
import unittest

from reefsim.scanned_coral import generate_scanned_coral


class ScannedCoralTests(unittest.TestCase):
    def test_bundled_files_match_provenance_manifest(self):
        root = Path(__file__).resolve().parents[1] / "assets" / "corals"
        manifest = json.loads((root / "manifest.json").read_text())
        for name, expected in manifest["files"].items():
            with self.subTest(file=name):
                data = (root / name).read_bytes()
                self.assertEqual(len(data), expected["bytes"])
                self.assertEqual(hashlib.sha256(data).hexdigest(), expected["sha256"])

    def test_all_health_states_produce_valid_bounded_geometry(self):
        for health in ("healthy", "bleached_alive", "dead"):
            with self.subTest(health=health):
                mesh = generate_scanned_coral(health, .4, .6, 26, preserve_aspect=True)
                size = len(mesh["points"])
                self.assertEqual(sum(mesh["counts"]), len(mesh["indices"]))
                self.assertTrue(all(0 <= i < size for i in mesh["indices"]))
                for key in ("normals", "colors", "uvs"):
                    self.assertEqual(len(mesh[key]), size)
                self.assertTrue(all(math.isfinite(v) for key in ("points", "normals", "colors", "uvs")
                                    for row in mesh[key] for v in row))
                self.assertGreaterEqual(min(p[2] for p in mesh["points"]), -1e-7)
                self.assertLessEqual(max(p[2] for p in mesh["points"]), .600001)
                self.assertLessEqual(max(math.hypot(p[0], p[1]) for p in mesh["points"]), .400001)
                self.assertTrue(all(abs(sum(v*v for v in n) - 1.) < 1e-6 for n in mesh["normals"]))

    def test_colours_do_not_change_structure_and_returned_meshes_are_independent(self):
        healthy = generate_scanned_coral("healthy", .3, .5, 26)
        bleached = generate_scanned_coral("bleached_alive", .3, .5, 26)
        self.assertEqual(healthy["points"], bleached["points"])
        self.assertNotEqual(healthy["colors"], bleached["colors"])
        healthy["points"][0] = (999., 999., 999.)
        fresh = generate_scanned_coral("healthy", .3, .5, 26)
        self.assertEqual(fresh["points"], bleached["points"])


if __name__ == "__main__":
    unittest.main()
