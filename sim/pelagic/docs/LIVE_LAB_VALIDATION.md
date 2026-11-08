# Reef Rescue AUV browser lab validation

Checked 8 November 2026. This evidence describes the browser laboratory, not the Isaac Sim solver or field deployment.

- 32 engine tests cover repeatability, compatible pairing, conserved fragment identity, dropped-fragment recovery, rejected cuts, placement retries, environmental holds/aborts, scene validation, both navigation routes, terrain clearance, exact scanned-coral contact coordinates, wildlife yielding, and shared habitat proxies.
- 14 Python API/server tests and 8 Worker tests cover real request shape with mocked provider responses, JPEG image validation, camera input hashes, bounds, cross-origin protection, unavailable credentials, rate limits, and explicit failures without invented decisions.
- Browser inspection confirmed the original interface design with Reef Rescue AUV naming, dense Smithsonian specimen geometry, sloping seabed, animated wildlife, updated gripper, route controls, sonar display, scene editing and camera evidence inspection.
- A browser baseline completed all four placements with 16 wildlife yields. Earlier drop and compound-fault browser episodes also completed; automated regression tests rerun the recovery cases after terrain and wildlife changes.
- The exported scene stays fixed across seeded tests. Seeds vary sampled cut quality, not every environmental parameter. The suite uses six conditions and a 600-second simulated-time budget. Its finite success rate is not a probability of real-world reliability.

## Architecture and limits

`terrain.mjs` supplies the same height field to the renderer and controller. `habitat.mjs` supplies matching layouts for 696 default habitat coral/rock proxies, in addition to the 84 registered colonies. The robot uses reduced thrust, buoyancy and drag with conservative collision/clearance models. Detailed mesh fracture, frictional grasp forces, material deformation, fluid coupling and adhesive chemistry are not solved.

The mission contact point is the transformed centroid of triangle 98258 on the preserved Smithsonian Pocillopora hero mesh, verified numerically against the rendered transform. A matched triangle is geometric evidence, not proof of a biologically suitable cutting/contact site.

Fish, crabs and a turtle have deterministic trajectories; their positions generate range contacts and affect robot motion. They are animated proxies, not behavioral ecology models. Sonar is geometric range sensing with simple rock occlusion, not a simulation of acoustic beam patterns, multipath or sediment scattering.

The tool-camera inspector renders a separate 768×576 camera into an offscreen target. Gemini requests include that JPEG and the structured sonar/mission packet; the response records the image hash. No live model call was made because credentials were not configured. Hosted static mode runs the scripted controller. The optional local server or Worker requires a separately configured server-side key.

## Reproduce

From `sim/pelagic` in the team repository:

```sh
python3 scripts/run_lab.py
node --test tests/lab-simulation.test.mjs tests/lab-worker.test.mjs
python3 -m unittest discover -s tests -p test_lab_server.py -v
```

Open http://127.0.0.1:8090/lab/. Use **Robustness tests → Run stress suite**, then export its per-run evidence. Use **Environment builder** to edit a paused scene; editing resets the episode so outcomes do not survive an environment change.

Surrounding scenery extends to a 160 m seabed with distant instanced scan thickets and limestone relief. This far-field context is outside the navigable working zone and is visual scenery, not additional calibrated physics. The shared working-area habitat remains the collision and sonar source. Browser QA confirmed the populated perimeter at zoomed-out orbit and top views. The final browser stress suite completed 18/18 modeled episodes.
