# Reef Rescue AUV browser lab validation

Checked 8 November 2026. This evidence describes the browser laboratory, not the Isaac Sim solver or field deployment.

- 25 Python backend/API tests pass, including actual Node recorder frames posted to the real local HTTP server. Browser QA separately verified a connected uplink with 45 frames acknowledged and retained by the base station, zero billed model calls, and explicit unconfigured model services.
- 72 Node checks pass across the engine, telemetry recorder and optional Worker. The combined engine/telemetry suite has 60 checks covering the existing 45 simulation regressions plus the robot/base contracts, inspection holds, replay/freshness checks, local plan validation and source separation.
- The offline architecture fixture completes four placements with explicitly mocked Gemma/Argon packets. This is contract integration coverage, not a live model or hardware test.
- A live `gemini-4-argon` adapter request on actual seed-42 simulation telemetry returned `proceed` with the `clearance` route in 16,693 ms. It explicitly received synthetic sensor/registry evidence without a camera or Gemma result. See [the saved result](ARGON_LIVE_CHECK.json). No live Gemma or cuOpt execution has been verified.
- Browser inspection confirms the original interface design with Reef Rescue AUV naming, dense Smithsonian specimen geometry, shared mixed topology, populated outer seabed, animated wildlife, connected gripper, manual pilot, randomized seeds, two route choices and the separate Robot & base panel.
- The current-wave regression records a modeled 5.31 N load exceeding the 5 N grip threshold, the actual held fragment dropping, same-ID recovery, and four verified placements. These are engineering proxies, not calibrated contact forces.
- The final regional layout passed a 1,000-seed generation test without sampling exceptions; this checks valid scene construction, not 1,000 completed missions. Five peak telemetry frames measured 53,108 bytes, below the uplink batch limit.
- Seeded tests use a finite selected scenario suite with a 600-second simulated-time budget. The exported scene stays fixed during an evaluation run; New reef also regenerates mission/habitat layout. Finite success rates are not real-world reliability estimates.

## Architecture and limits

`terrain.mjs` supplies the same height field to the renderer and controller. `habitat.mjs` supplies matching layouts for 620 irregularly allocated habitat corals and filtered rock proxies, in addition to the 84 registered colonies. The robot uses reduced thrust, buoyancy and drag with conservative collision/clearance models. Detailed mesh fracture, frictional grasp forces, material deformation, fluid coupling and adhesive chemistry are not solved.

The mission contact point is the transformed centroid of triangle 98258 on the preserved Smithsonian Pocillopora hero mesh, verified numerically against the rendered transform. A matched triangle is geometric evidence, not proof of a biologically suitable cutting/contact site.

Fish, crabs and a turtle have deterministic trajectories; their positions generate range contacts and affect robot motion. They are animated proxies, not behavioral ecology models. Sonar is geometric range sensing with simple rock occlusion, not a simulation of acoustic beam patterns, multipath or sediment scattering.

The tool-camera inspector renders a separate 768×576 camera into an offscreen target. Gemini requests include that JPEG and the structured sonar/mission packet; the response records the image hash. The separate Argon telemetry-only live check is described above; camera-model verification remains outstanding. Hosted static mode runs the scripted controller. The optional local server or Worker requires a separately configured server-side key.

## Reproduce

From `sim/pelagic` in the team repository:

```sh
python3 scripts/run_lab.py
node --test tests/lab-simulation.test.mjs tests/lab-worker.test.mjs tests/lab-telemetry.test.mjs
python3 -m unittest discover -s tests -p test_lab_server.py -v
```

Open http://127.0.0.1:8090/lab/. Use **Robustness tests → Run stress suite**, then export its per-run evidence. Use **Environment builder** to edit a paused scene; editing resets the episode so outcomes do not survive an environment change.

Surrounding scenery extends to a 160 m seabed with distant instanced scan thickets and limestone relief. This far-field context is outside the navigable working zone and is visual scenery, not additional calibrated physics. The shared working-area habitat remains the collision and sonar source. Browser QA confirmed the populated perimeter at zoomed-out orbit and top views. The final browser stress suite completed 18/18 modeled episodes.
