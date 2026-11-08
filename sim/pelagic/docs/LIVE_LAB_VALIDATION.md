# Reef Rescue AUV browser lab validation

Checked 8 November 2026. This evidence describes the browser laboratory, not the Isaac Sim solver or field deployment.

- **146 automated checks pass:** 99 Node checks across engine, telemetry, semantic memory, cross-language pipeline, Mission Control and Worker; 29 lab-server tests; four cuOpt-adapter tests; 12 team-feed bridge tests; two canonical dashboard tests. Model/solver contract tests use explicit doubles unless a live check is identified separately. Tests do not establish live inference or calibrated physics.
- The cross-language pipeline drives the actual Python adapters from the browser engine with clearly mocked Gemma, Argon and cuOpt transports: nine matched captures, five plans, one drop/recovery and four verified placements. Target binding, stale-frame rejection, physical rescans and full-stack route provenance are enforced.
- The owner-private hosted Site now serves its authenticated Worker gateway and static assets together. Browser QA verified the real Modal architecture response, actual telemetry receipt, the expandable tool/forward PiP and approximately 60 FPS on the tested desktop viewport.
- NVIDIA cuOpt 26.10 completed a real GPU warmup solve on Modal. Actual Gemma requests on UV-lit and white-light RGB robot images returned `unknown` with zero confidence, leaving health approval blocked; see [the saved UV trace](evidence/gemma_uv_uncertainty.json). These responses verify inference transport, not accepted coral recognition. No full live restoration episode has completed. Readiness, inference response, health acceptance and mission completion are separate states.
- A previous live `gemini-4-argon` adapter request on actual seed-42 simulation telemetry returned `proceed` with the `clearance` route in 16,693 ms. It received synthetic sensor/registry evidence without a camera or Gemma result. See [the saved result](ARGON_LIVE_CHECK.json).
- Browser inspection confirms the original interface design with Reef Rescue AUV naming, dense Smithsonian specimen geometry, shared mixed topology, populated outer seabed, animated wildlife, connected gripper, manual pilot, randomized seeds, two route choices and the separate Robot & base panel.
- The current-wave regression records a modeled 5.31 N load exceeding the 5 N grip threshold, the actual held fragment dropping, same-ID recovery, and four verified placements. These are engineering proxies, not calibrated contact forces.
- The final regional layout passed a 1,000-seed generation test without sampling exceptions; this checks valid scene construction, not 1,000 completed missions. Five peak telemetry frames measured 53,108 bytes, below the uplink batch limit.
- Seeded tests use a finite selected scenario suite with a 600-second simulated-time budget. The exported scene stays fixed during an evaluation run; New reef also regenerates mission/habitat layout. Finite success rates are not real-world reliability estimates.

## Complete live uncertainty chain — verified safe abort

**The complete live uncertainty chain is verified:** four fresh white-light Gemma captures returned `unknown`/0 confidence; four actual cuOpt solves and Argon plans requested three inspections, then a safe abort at **100.433 simulated seconds**. No harvesting, placements or collisions occurred. Telemetry acknowledged **332 frames**, with **162 skipped**. The final request-matched `decision-4` solve used cuOpt **26.10.0**, reported `SUCCESS` in **252 ms** and objective **0.55390667915**. Argon consumed structured Gemma observations and telemetry, not the JPEG. See [saved live safe-abort evidence](evidence/live_stack_safe_abort.json). **Accepted health recognition, successful live restoration and live fragment-drop recovery remain unverified.**

## Aryan Mission Control and team-source integration

Aryan Patel's dashboard capabilities are embedded in the lab's Mission evidence workspace: semantic map selection, health counts/filters, colony details, selectable decisions and evidence/outcome inspection, stable historical selection and independent view pause. The standalone dashboard and frozen registry/decision contracts remain intact. Browser map selection highlights the corresponding 3D colony; external sources remain read-only and do not command or replace the browser simulation.

The bundled **Recorded team mission** contains actual prior `mission.runner` / team FSM output: **24 colonies, 10 decisions, one mechanically treated recipient and one dislodgement**, with recorded `MISSION_COMPLETE`. This is reduced-physics, synthetic pre-mapped perception—not the current browser mission or a live Gemma run. No camera frame was saved; the panel displays that absence. The asset is `web/lab/assets/team-mission-recorded.json`. Browser QA verified the recorded source's 24 colonies and 10 decisions, health filters, colony selection, retained decision history and independent view pause. The live team source correctly showed unconfigured status without substituting sample data. The recording remains synthetic pre-mapped/reduced-physics evidence with one treated recipient and one dislodgement; no camera frame was saved.

The **Team mission** source uses the read-only `TEAM_RUN_DIR` bridge and canonical dashboard readers. Automated checks cover file refresh, stale/malformed sources, last-good-state retention, payload bounds and unsafe paths. A missing optional camera does not discard valid registry/decision evidence. Component HTTP checks also returned 200 for the corrected Modal `/v1/models` route at 12:26:38 and for team-state; HTTP success alone does not prove image recognition or a restored mission. Setup and limits are in [LIVE_LAB.md](LIVE_LAB.md).

Mission Control adapter tests run an actual browser episode: secured but unverified fragments do not count as treated; verified placement maps to `TREATED`, never `RECOVERED`. Known registry health has no invented confidence or detection boxes. Evidence is bounded, source-labelled and excludes credentials/raw images.

The new uncertainty-review fixture permits a target-matched unknown colony observation to request only a fresh inspection retry or abort, with at most three retries. Manual rescan during uncertainty reacquires colony views instead of treating an attached fragment as lost. Unknown evidence cannot authorize harvest. The complete real Argon/cuOpt uncertainty-review/rescan sequence is now verified; see the live result above.

## Architecture and limits

`terrain.mjs` supplies the same height field to the renderer and controller. `habitat.mjs` supplies matching layouts for 620 irregularly allocated habitat corals and filtered rock proxies, in addition to the 84 registered colonies. The robot uses reduced thrust, buoyancy and drag with conservative collision/clearance models. Detailed mesh fracture, frictional grasp forces, material deformation, fluid coupling and adhesive chemistry are not solved.

The mission contact point is the transformed centroid of triangle 98258 on the preserved Smithsonian Pocillopora hero mesh, verified numerically against the rendered transform. A matched triangle is geometric evidence, not proof of a biologically suitable cutting/contact site.

Fish, crabs and a turtle have deterministic trajectories; their positions generate range contacts and affect robot motion. They are animated proxies, not behavioral ecology models. Sonar is geometric range sensing with simple rock occlusion, not a simulation of acoustic beam patterns, multipath or sediment scattering.

The tool-camera inspector renders a separate 768×576 camera into an offscreen target. The always-visible PiP uses a bounded 384×288 view at 5 Hz; the expanded inspector updates at 2 Hz. Tool and forward cameras use independent robot camera poses and exclude spectator overlays; they share scene fog, materials and lighting rather than independently calibrated spectral/attenuation models. Actual model captures retain image hashes and target/capture identities. Persistent scene-specific memory stores historical Gemma observations, with seven-day expiry and explicit import/export/clear; it never authorizes a fresh action. Modal perception is remote GPU inference, not an onboard hardware measurement.

## Reproduce

From `sim/pelagic` in the team repository:

```sh
python3 scripts/run_lab.py
node --test tests/lab-*.test.mjs
python3 -m unittest discover -s tests -p test_lab_server.py -v
python3 -m unittest discover -s tests -p test_cuopt_route_adapter.py -v
python3 -m unittest discover -s tests -p test_team_feed.py -v
python3 -m unittest discover -s ../../dashboard -p test_server.py -v
```

Open http://127.0.0.1:8090/lab/. Use **Robustness tests → Run stress suite**, then export its per-run evidence. Use **Environment builder** to edit a paused scene; editing resets the episode so outcomes do not survive an environment change.

Surrounding scenery extends to a 160 m seabed with distant instanced scan thickets and limestone relief. This far-field context is outside the navigable working zone and is visual scenery, not additional calibrated physics. The shared working-area habitat remains the collision and sonar source. Browser QA confirmed the populated perimeter at zoomed-out orbit and top views. The final browser stress suite completed 18/18 modeled episodes.
