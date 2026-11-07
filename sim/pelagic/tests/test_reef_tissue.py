import hashlib
import json
from pathlib import Path
import unittest

from PIL import Image, ImageStat

from reefsim.reef_tissue import MATERIAL_ROOT, PHENOTYPES, material_files, tissue_color


class ReefTissueTests(unittest.TestCase):
    def test_bundled_maps_and_source_provenance_match(self):
        manifest=json.loads((MATERIAL_ROOT/"manifest.json").read_text())
        for name,record in manifest["files"].items():
            with self.subTest(file=name):
                payload=(MATERIAL_ROOT/name).read_bytes()
                self.assertEqual(len(payload),record["bytes"])
                self.assertEqual(hashlib.sha256(payload).hexdigest(),record["sha256"])
        self.assertFalse(manifest["geometry_changed"])
        self.assertFalse(manifest["uv_layout_changed"])
        normal=Path(material_files("healthy")["normal"])
        self.assertEqual(hashlib.sha256(normal.read_bytes()).hexdigest(),manifest["source_normal_sha256"])

    def test_maps_have_detail_and_separate_living_bleached_dead_states(self):
        for phenotype in PHENOTYPES:
            brightness=[]
            for health in ("healthy","bleached_alive","dead"):
                files=material_files(health,phenotype)
                diffuse=Image.open(files["diffuse"])
                self.assertEqual(diffuse.size,(1024,1024))
                gray=ImageStat.Stat(diffuse.convert("L"))
                self.assertGreater(gray.stddev[0],gray.mean[0]*.10,
                                   "Uniform tint would lose calice detail")
                brightness.append(gray.mean[0])
                roughness=Image.open(files["roughness"])
                low,high=roughness.getextrema()
                self.assertGreaterEqual(low,170)
                self.assertGreater(high-low,8)
            self.assertGreater(brightness[1],brightness[0]+20.)
            self.assertGreater(brightness[0],brightness[2]+8.)
        pale=Image.open(material_files("bleached_alive","tan")["diffuse"])
        self.assertGreater(ImageStat.Stat(pale).mean[0],ImageStat.Stat(pale).mean[2]+15.)

    def test_runtime_contract_and_muted_scenery_palette(self):
        self.assertEqual(material_files("healthy")["phenotype"],"tan")
        for seed in range(30):
            for health in ("healthy","bleached_alive","dead"):
                colour=tissue_color(health,seed)
                self.assertTrue(all(0<=value<=1 for value in colour))
                self.assertEqual(colour,tissue_color(health,seed))
        with self.assertRaises(ValueError):material_files("unknown")
        with self.assertRaises(ValueError):material_files("healthy","neon")
        with self.assertRaises(ValueError):tissue_color("healthy",True)


if __name__ == "__main__":
    unittest.main()
