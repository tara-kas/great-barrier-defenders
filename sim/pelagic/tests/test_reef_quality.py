import copy
import math
import unittest

from reefsim.reef_quality import plan_reef_quality, generate_quality_coral
from reefsim.reef_landscape import build_reef_scenery
from reefsim.core import ReefSimulation


def colony(identifier="reef", seed=26, health="healthy", x=0., y=0.):
    return {"id": identifier, "seed": seed, "health": health,
            "radius": .32, "height": .36, "position": [x, y, 0.],
            "morphology": "plating"}


class ReefQualityTests(unittest.TestCase):
    def test_full_population_budget_and_worksite_distribution(self):
        sim = ReefSimulation()
        snapshot = sim.snapshot()
        colonies = build_reef_scenery(sim.config, snapshot)
        plan = plan_reef_quality(colonies, snapshot, sim.config)
        self.assertEqual(plan, plan_reef_quality(colonies, snapshot, sim.config))
        self.assertEqual(len(plan), len(colonies))
        self.assertLessEqual(sum(s["triangles"] for s in plan.values()), 14_000_000)
        heroes = [s for s in plan.values() if s["detail"] == "hero"]
        self.assertEqual(len(heroes), 24)
        self.assertGreater(len({s["anchor"] for s in heroes}), 12)
        self.assertTrue(all(s["material"] == "tissue" and s["uv_mode"] == "source_atlas" for s in heroes))
        self.assertEqual({s["asset"] for s in plan.values()}, {"pocillopora_damicornis", "acropora_secale"})

    def test_complete_scans_fit_existing_envelopes_and_keep_valid_normals(self):
        for seed in (25, 26):
            for health in ("healthy", "bleached_alive", "dead"):
                with self.subTest(seed=seed, health=health):
                    c = colony(seed=seed, health=health)
                    spec = plan_reef_quality([c], {}, {"render":{"reef_hero_colonies":0}})[c["id"]]
                    result = generate_quality_coral(c, spec)
                    mesh = result["mesh"]
                    self.assertGreater(result["triangles"], 14000)
                    self.assertEqual(len(mesh["points"]), len(mesh["normals"]))
                    self.assertEqual(len(mesh["points"]), len(mesh["uvs"]))
                    self.assertEqual(len(mesh["points"]), len(mesh["colors"]))
                    self.assertEqual(sum(mesh["counts"]), len(mesh["indices"]))
                    self.assertTrue(all(0 <= i < len(mesh["points"]) for i in mesh["indices"]))
                    self.assertTrue(all(math.isfinite(v) for p in mesh["points"] for v in p))
                    self.assertLessEqual(max(math.hypot(p[0],p[1]) for p in mesh["points"]), c["radius"]+1e-9)
                    self.assertAlmostEqual(min(p[2] for p in mesh["points"]), 0.)
                    self.assertLessEqual(max(p[2] for p in mesh["points"]), c["height"]+1e-9)
                    self.assertGreater(max(p[2] for p in mesh["points"]), .20)
                    for normal in mesh["normals"]:
                        self.assertAlmostEqual(sum(v*v for v in normal), 1., places=6)

    def test_bleaching_keeps_living_geometry_but_has_residual_tissue(self):
        results = {}
        for health in ("healthy", "bleached_alive", "dead"):
            c = colony(health=health)
            spec = plan_reef_quality([c], {}, {"render":{"reef_hero_colonies":0}})[c["id"]]
            results[health] = generate_quality_coral(c, spec)["mesh"]
        self.assertEqual(results["healthy"]["points"], results["bleached_alive"]["points"])
        self.assertNotEqual(results["healthy"]["points"], results["dead"]["points"])
        bright = lambda health: sum(sum(c)/3 for c in results[health]["colors"])/len(results[health]["colors"])
        self.assertGreater(bright("bleached_alive"), bright("healthy")+.15)
        self.assertGreater(bright("bleached_alive"), bright("dead")+.25)
        pale_colors = results["bleached_alive"]["colors"]
        self.assertGreater(max(c[0] for c in pale_colors)-min(c[0] for c in pale_colors), .10)

    def test_original_uvs_are_only_bound_to_original_geometry(self):
        c = colony()
        spec = plan_reef_quality([c], {})[c["id"]]
        result = generate_quality_coral(c, spec)
        self.assertEqual(result["material"], "tissue")
        self.assertGreater(result["triangles"], 140000)
        self.assertEqual(set(result["mesh"]["colors"]), {(1.,1.,1.)})
        from reefsim.pocillopora_scan import generate_pocillopora_scan
        original = generate_pocillopora_scan("healthy", c["radius"], c["height"], c["seed"], detail="hero")
        self.assertEqual(original["uvs"], result["mesh"]["uvs"])

    def test_seed_variants_are_repeatable_and_do_not_mutate_cached_sources(self):
        c = colony()
        options = {"render":{"reef_hero_colonies":0}}
        spec = plan_reef_quality([c], {}, options)[c["id"]]
        first = generate_quality_coral(c, spec)
        self.assertEqual(first, generate_quality_coral(c, spec))
        first["mesh"]["points"][0] = (999.,999.,999.)
        self.assertNotEqual(first, generate_quality_coral(c, spec))
        other = copy.deepcopy(c)
        other["seed"] += 5
        self.assertNotEqual(generate_quality_coral(c,spec)["mesh"]["points"], generate_quality_coral(other,spec)["mesh"]["points"])

    def test_budget_validation_and_stable_distant_lod(self):
        cols = [colony(str(i), seed=26, x=float(i)) for i in range(20)]
        cfg = {"render":{"reef_triangle_budget":320000, "reef_hero_colonies":24}}
        plan = plan_reef_quality(cols, {"corals":[{"position":[0.,0.,0.]}]}, cfg)
        self.assertLessEqual(sum(s["triangles"] for s in plan.values()), 320000)
        self.assertEqual(plan["19"]["asset"], "acropora_secale")
        for render in ({"reef_triangle_budget":1}, {"reef_hero_colonies":49}, {"reef_triangle_budget":float("nan")}):
            with self.assertRaises(ValueError):
                plan_reef_quality(cols, {}, {"render":render})
        with self.assertRaises(ValueError):
            plan_reef_quality([cols[0],cols[0]], {})


if __name__ == "__main__":
    unittest.main()
