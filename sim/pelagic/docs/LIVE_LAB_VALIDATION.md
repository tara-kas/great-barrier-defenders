# Reef Rescue AUV browser lab validation

Checked 8 November 2026. This evidence describes the browser laboratory, not the Isaac Sim solver or field deployment.

- **120 Node checks pass** across the current browser/engine, telemetry, memory, cross-language pipeline, Mission Control and Worker suites.
- **38 Python backend checks pass**, including strict camera/appearance validation, tracked image-focus coordinates, local planning, bounded Argon assistance and terminal review.
- **11 live-stream/feed/finalizer checks pass separately.** These test snapshot transport/provenance and capture/finalizer validation; they are not eleven successful live robot missions. These three counts describe distinct test scopes. Model/solver contract tests use explicit doubles unless a live check is identified separately.
- The cross-language pipeline drives the actual Python local policy and browser engine with clearly mocked Gemma and cuOpt transports through loose-fragment pickup, one drop/recovery and four verified placements. It asserts that `/plan` makes no Argon call. This checks integration and local gates, not live-model restoration success or live `/assist` behavior.
- The owner-private hosted Site serves its authenticated Worker gateway and static assets together. Browser QA verified a real Modal architecture response, actual telemetry receipt and the expandable tool/forward PiP. Earlier approximately 60 FPS was measured only on the tested desktop viewport; it is not a general performance guarantee.
- NVIDIA cuOpt 26.10 completed a real GPU warmup solve on Modal. Earlier actual Gemma browser frames passed the new `appearance/v1` colony gates: pale/bleached recipient and pigmented source, with biological health still unknown and viability supplied only by independent registry eligibility. An earlier loose-fragment capture held because gripper state was unknown; see [the recorded fragment hold](evidence/live_fragment_visibility_hold.json). A later actual run passed fresh fragment/gripper evidence and completed one mechanical placement, documented below. Accepted colony appearance alone never authorizes pickup.
- The earlier [UV uncertainty trace](evidence/gemma_uv_uncertainty.json), [Argon planning call](ARGON_LIVE_CHECK.json), and [four-frame safe-abort trace](evidence/live_stack_safe_abort.json) belong to superseded contracts or mission-planning roles. They are preserved as historical evidence, not relabelled as the current architecture.
- Browser inspection confirms the original interface design with Reef Rescue AUV naming, dense Smithsonian specimen geometry, shared mixed topology, populated outer seabed, animated wildlife, connected gripper, manual pilot, randomized seeds, two route choices and the separate Robot & base panel.
- The current-wave regression records a modeled 5.31 N load exceeding the 5 N grip threshold, the actual held fragment dropping, same-ID recovery, and four verified placements. These are engineering proxies, not calibrated contact forces.
- An earlier regional layout passed a 1,000-seed generation test without sampling exceptions; this checks valid scene construction, not 1,000 completed missions. Five peak telemetry frames measured 53,108 bytes, below the uplink batch limit.
- Seeded tests use a finite selected scenario suite with a 600-second simulated-time budget. The exported scene stays fixed during an evaluation run; New reef also regenerates mission/habitat layout. Finite success rates are not real-world reliability estimates.

## Current live checkpoint — first completed live browser placement

The complete actual episode in `output/video/final/full-episode.json` was independently inspected: `completed:true`, phase `complete`, and **one mechanically verified placement at T+80.55 simulated seconds**. The concise [completed-placement evidence](evidence/live_stack_completed_placement.json) records the live provider/controller sequence. This is the first verified complete browser episode using actual Gemma, bounded Argon assistance, cuOpt and the inspectable local policy; it is not a mocked-model run or biological-restoration claim.

- Actual Gemma responses took **2.687–3.201 seconds** in the retained transport log. An initial source-colony observation was rejected because the object/gripper evidence was inconsistent; the mission held rather than accepting the appearance score alone.
- Actual Argon `/assist` returned **RESCAN in 22.700 seconds**. Fresh recipient, source-colony and loose-fragment views were then obtained; the accepted fragment view reported a visible piece and empty gripper.
- A sensor dropout was injected at **T+36.38**, triggering a local hold. Conditions recovered and the same mission state resumed at **T+44.40**. This is sensor-dropout adaptation, not fragment-drop recovery.
- The actual cuOpt/local-planner response took **689 ms**, selected the declared direct corridor and proposed proceed. Gemma evidence, registered eligibility and local motion/contact checks remained authoritative.
- **`donor-1-fragment-1`** was collected from existing registered loose stock at **T+65.083** and mechanically verified on `recipient-1` at **T+80.55**. Final metrics: **1 placement, 0 drops, 0 recoveries, 0 damage and 0 collisions**.

This establishes one completed live browser placement with uncertainty escalation and a sensor hold/resume. **Live current-induced fragment-drop recovery remains unverified**; zero drops/recoveries cannot establish it. The independent Isaac stream still uses its own analytical controller, and this browser completion does not establish Isaac closed-loop Gemma control, physical contact fidelity or biological recovery.

## Earlier v13 uncertainty run — verified safe abort

In an earlier v13 run, actual mission uncertainty was escalated to Argon through `/assist`. It returned **RESCAN twice, then HOLD**; the unresolved hold subsequently reached a timeout and the local controller safely aborted. This verifies actual bounded issue advice and conservative timeout behavior. That failed run does **not** establish successful pickup or placement. The subsequent completed-placement episode above supplies that separate evidence; live fragment-drop recovery still remains unverified.

The current roles are distinct:

- `/plan`: inspectable local policy plus actual configured cuOpt corridor evaluation; no Argon call.
- `/assist`: Argon advice during a held/paused nonterminal issue, strictly rescan/hold/abort with at most three provider attempts per episode. It cannot authorize proceeding or override camera, registry or local safety gates.
- `/review`: advisory Argon summary/recommendations after completion or abort, with no control authority.

`appearance/v1` describes visible object geometry and surface appearance. Scores are uncalibrated; `health:"unknown"` and `viabilityKnown:false` remain intentional. `imageFocus` coordinates are known tracked positions projected through the capture camera, not detected boxes or validated localization. Target/gripper ambiguity still holds the mission. Startup readiness, a successful provider reply, accepted appearance, accepted grasp evidence and completed recovery are separate checkpoints.

The earlier live safe-abort trace at 100.433 simulated seconds used in-mission Argon plans: four unknown/zero-confidence captures, three retries and abort, with no harvesting or placement. Its 332 acknowledged telemetry frames, 162 skipped frames and final cuOpt solve are historical measurements for that specific run, not v13 statistics.

## Aryan Mission Control and team-source integration

Aryan Patel's dashboard capabilities are embedded in the lab's Mission evidence workspace: semantic map selection, health counts/filters, colony details, selectable decisions and evidence/outcome inspection, stable historical selection and independent view pause. The standalone dashboard and frozen registry/decision contracts remain intact. Browser map selection highlights the corresponding 3D colony; external sources remain read-only and do not command or replace the browser simulation.

The bundled **Recorded team mission** contains actual prior `mission.runner` / team FSM output: **24 colonies, 10 decisions, one mechanically treated recipient and one dislodgement**, with recorded `MISSION_COMPLETE`. This is reduced-physics, synthetic pre-mapped perception—not the current browser mission or a live Gemma run. No camera frame was saved; the panel displays that absence. The asset is `web/lab/assets/team-mission-recorded.json`. Browser QA verified the recorded source's 24 colonies and 10 decisions, health filters, colony selection, retained decision history and independent view pause. Before the relay was configured, the live team source correctly showed unconfigured status without substituting sample data. The recording remains synthetic pre-mapped/reduced-physics evidence with one treated recipient and one dislodgement; no camera frame was saved.

The **Team mission** source supports the read-only `TEAM_RUN_DIR` bridge and canonical dashboard readers, plus an authenticated live Isaac snapshot relay. Actual Isaac RTX frame/state streaming has been verified in the hosted view. The source labels its observations and events as an independent analytical controller, not Gemma-controlled browser behavior; it supplies no fabricated detection boxes. Browser and Isaac worlds retain separate state and physics, and this read-only relay sends no robot commands. Automated checks cover file refresh, stale/malformed sources, last-good-state retention, payload bounds and unsafe paths. A missing optional camera does not discard valid registry/decision evidence. Component HTTP checks also returned 200 for the corrected Modal `/v1/models` route at 12:26:38 and for team-state; HTTP success alone does not prove image recognition or a restored mission. Setup and limits are in [LIVE_LAB.md](LIVE_LAB.md).

Mission Control adapter tests run the browser engine with synthetic scenario inputs: secured but unverified fragments do not count as treated; verified placement maps to `TREATED`, never `RECOVERED`. Known registry health has no invented confidence or detection boxes. Evidence is bounded, source-labelled and excludes credentials/raw images.

The new uncertainty-review fixture permits a target-matched unknown colony observation to request only a fresh inspection retry or abort, with at most three retries. Manual rescan during uncertainty reacquires colony views instead of treating an attached fragment as lost. Unknown evidence cannot authorize harvest. The current actual Argon assistance sequence is described above; it is distinct from the earlier Argon/cuOpt mission-planning sequence. Neither establishes successful live restoration.

## Architecture and limits

`terrain.mjs` supplies the same height field to the renderer and controller. `habitat.mjs` supplies matching layouts for 620 irregularly allocated habitat corals and filtered rock proxies, in addition to the 84 registered colonies. The robot uses reduced thrust, buoyancy and drag with conservative collision/clearance models. Detailed mesh fracture, frictional grasp forces, material deformation, fluid coupling and adhesive chemistry are not solved.

The registered colony contact point uses the transformed centroid of triangle 98258 on the preserved Smithsonian Pocillopora hero mesh, verified numerically against the rendered transform. Current browser missions collect already detached, permitted loose stock rather than cutting attached healthy coral. A matched triangle is geometric evidence, not biological eligibility or proof of a suitable treatment site.

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
python3 -m unittest discover -s tests -p test_live_feed.py -v
python3 -m unittest discover -s tests -p test_live_stream_capture.py -v
python3 -m unittest discover -s ../../dashboard -p test_server.py -v
```

Open http://127.0.0.1:8090/lab/. Use **Robustness tests → Run stress suite**, then export its per-run evidence. Use **Environment builder** to edit a paused scene; editing resets the episode so outcomes do not survive an environment change.

Surrounding scenery extends to a 160 m seabed with distant instanced scan thickets and limestone relief. This far-field context is outside the navigable working zone and is visual scenery, not additional calibrated physics. The shared working-area habitat remains the collision and sonar source. Browser QA confirmed the populated perimeter at zoomed-out orbit and top views. An earlier browser stress suite completed 18/18 modeled episodes. That finite reduced-model result is not a live-model success rate or evidence of live current-induced fragment-drop recovery.

## Final follow-up live attempt

A later actual-model attempt classified the source view as a coral fragment rather than a colony. The visual gate remained closed; Argon assistance returned a gateway failure, and the 90-second assistance hold ended in abort at **114.65 simulated seconds**, with zero placements/drops/recoveries/collisions and one wildlife yield. See [the saved follow-up trace](evidence/live_latest_uncertainty_abort.json). This failure does not invalidate the independently saved completed-placement episode, but confirms that repeatable live perception and current-induced recovery remain acceptance work. The final production UI requires both Gemma and cuOpt and exposes no presentation or local bypass. Its 120 Node checks passed; backend and feed/capture suites passed separately.
