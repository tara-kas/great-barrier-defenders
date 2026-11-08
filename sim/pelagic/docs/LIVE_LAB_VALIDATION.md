# Reef Rescue AUV browser lab validation

Checked 8 November 2026. This evidence describes the browser laboratory, not the Isaac Sim solver or field deployment.

- **119 automated checks pass:** 86 Node checks across engine, telemetry, semantic memory, cross-language pipeline and Worker; 29 Python backend/API tests; four native-cuOpt protocol tests using explicit solver doubles. Tests do not establish live inference or calibrated physics.
- The cross-language pipeline drives the actual Python adapters from the browser engine with clearly mocked Gemma, Argon and cuOpt transports: nine matched captures, five plans, one drop/recovery and four verified placements. Target binding, stale-frame rejection, physical rescans and full-stack route provenance are enforced.
- The owner-private hosted Site now serves its authenticated Worker gateway and static assets together. Browser QA verified the real Modal architecture response, actual telemetry receipt, the expandable tool/forward PiP and approximately 60 FPS on the tested desktop viewport.
- NVIDIA cuOpt 26.10 completed a real GPU warmup solve on Modal. Actual Gemma inference on a robot image returned an uncertain observation and correctly held; see [the saved trace](evidence/gemma_uv_uncertainty.json). The complete live camera-to-action episode is still being checked. Readiness and actual inference are separate UI states.
- A previous live `gemini-4-argon` adapter request on actual seed-42 simulation telemetry returned `proceed` with the `clearance` route in 16,693 ms. It received synthetic sensor/registry evidence without a camera or Gemma result. See [the saved result](ARGON_LIVE_CHECK.json).
- Browser inspection confirms the original interface design with Reef Rescue AUV naming, dense Smithsonian specimen geometry, shared mixed topology, populated outer seabed, animated wildlife, connected gripper, manual pilot, randomized seeds, two route choices and the separate Robot & base panel.
- The current-wave regression records a modeled 5.31 N load exceeding the 5 N grip threshold, the actual held fragment dropping, same-ID recovery, and four verified placements. These are engineering proxies, not calibrated contact forces.
- The final regional layout passed a 1,000-seed generation test without sampling exceptions; this checks valid scene construction, not 1,000 completed missions. Five peak telemetry frames measured 53,108 bytes, below the uplink batch limit.
- Seeded tests use a finite selected scenario suite with a 600-second simulated-time budget. The exported scene stays fixed during an evaluation run; New reef also regenerates mission/habitat layout. Finite success rates are not real-world reliability estimates.

## Architecture and limits

`terrain.mjs` supplies the same height field to the renderer and controller. `habitat.mjs` supplies matching layouts for 620 irregularly allocated habitat corals and filtered rock proxies, in addition to the 84 registered colonies. The robot uses reduced thrust, buoyancy and drag with conservative collision/clearance models. Detailed mesh fracture, frictional grasp forces, material deformation, fluid coupling and adhesive chemistry are not solved.

The mission contact point is the transformed centroid of triangle 98258 on the preserved Smithsonian Pocillopora hero mesh, verified numerically against the rendered transform. A matched triangle is geometric evidence, not proof of a biologically suitable cutting/contact site.

Fish, crabs and a turtle have deterministic trajectories; their positions generate range contacts and affect robot motion. They are animated proxies, not behavioral ecology models. Sonar is geometric range sensing with simple rock occlusion, not a simulation of acoustic beam patterns, multipath or sediment scattering.

The tool-camera inspector renders a separate 768×576 camera into an offscreen target. The always-visible PiP uses a bounded 384×288 view at 5 Hz; the expanded inspector updates at 2 Hz. Tool and forward cameras use independent robot optics and exclude spectator overlays. Actual model captures retain image hashes and target/capture identities. Persistent scene-specific memory stores historical Gemma observations, with seven-day expiry and explicit import/export/clear; it never authorizes a fresh action. Modal perception is remote GPU inference, not an onboard hardware measurement.

## Reproduce

From `sim/pelagic` in the team repository:

```sh
python3 scripts/run_lab.py
node --test tests/lab-*.test.mjs
python3 -m unittest discover -s tests -p test_lab_server.py -v
python3 -m unittest discover -s tests -p test_cuopt_route_adapter.py -v
```

Open http://127.0.0.1:8090/lab/. Use **Robustness tests → Run stress suite**, then export its per-run evidence. Use **Environment builder** to edit a paused scene; editing resets the episode so outcomes do not survive an environment change.

Surrounding scenery extends to a 160 m seabed with distant instanced scan thickets and limestone relief. This far-field context is outside the navigable working zone and is visual scenery, not additional calibrated physics. The shared working-area habitat remains the collision and sonar source. Browser QA confirmed the populated perimeter at zoomed-out orbit and top views. The final browser stress suite completed 18/18 modeled episodes.
