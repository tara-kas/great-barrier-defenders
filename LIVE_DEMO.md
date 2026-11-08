# Reef Rescue AUV — interactive simulation lab

The browser lab preserves the project design system and uses the Reef Rescue AUV name. It is an editable case-presentation and controller-recovery environment alongside the Isaac simulator.

**Hosted demo:** https://reef-rescue-auv-lab.harrish-ayyanar.chatgpt.site (owner-private; model-guided production; errors hold, rescan or abort).

```sh
cd sim/pelagic
python3 scripts/run_lab.py
```

Open http://127.0.0.1:8090/lab/.

The lab includes manual robot piloting, seeded healthy/bleached reef regions with mixed transitions, visible continuous current vectors, UV exposure gates, current-load grip loss and same-fragment recovery, scanned coral thickets, a sloping textured seabed, a connected gripper, fish/crab/turtle avoidance, two actual navigation routes, simulated sonar, editable colonies/obstacles, four loose-fragment setback controls, recovery traces, and downloadable stress results. Use the live tool/forward camera PiP and enlarge it to inspect the robot view. Brighter white and UV lamps illuminate real rendered frames. Model sends/replies, timings and route decisions appear in the activity log; scene-specific semantic memory can be saved and exported. The Robot & base panel separates Gemma camera perception, the telemetry uplink, inspectable mission policy and NVIDIA cuOpt route optimization (required in full-stack mode), with Gemini Argon providing bounded advice during held mission issues and review after completion or abort. Ordinary `/plan` remains local policy plus cuOpt; Argon `/assist` can recommend only rescan, hold or abort, with at most three provider attempts per episode. It cannot authorize pickup, issue actuator commands or override Gemma/registry/safety gates. Terminal `/review` remains advisory only. The hosted Worker connects to the private Modal Gemma/cuOpt gateway and Gemini Argon; local deployments use the documented adapters. The UI checks the model stack; unavailable services hold the mission. There is no local/scripted, partial-stack or presentation-only production bypass. Manual Pilot and operator fault injection remain explicitly human controls. No key is shipped to the browser.

## Aryan’s mission evidence, embedded

The **Mission evidence** workspace brings the registry map, health filters, linked colony selection, stable historical decision inspection, evidence/outcome details and independent view pause from Aryan Patel’s dashboard into the lab design. His original dashboard and commits are preserved unchanged. The bridge reuses `dashboard/server.py` readers rather than introducing a competing parser.

Choose **Lab simulation**, **Live team mission · read only**, or **Recorded team mission**. The bundled recorded team run contains 24 colonies, 10 decisions, one dislodgement and one mechanically treated recipient; it is explicitly labelled reduced-physics, synthetic premapped evidence, with no camera frame. It is not a live Gemma success. Live files can be connected with `python3 scripts/run_lab.py --team-run-dir /absolute/path/to/mission-output`; the hosted deployment now receives actual Isaac RTX camera frames and state through an authenticated relay. The read-only source never commands the browser robot or the Isaac robot. Actual live Isaac frame/state transport has been verified; its analytical controller and synthetic scene observations are explicitly separate from the browser’s Gemma/local-policy/cuOpt controller. Neither episode substitutes for evidence of the other.

The browser engine is independent of the authoritative team mission/Isaac stack. It uses reduced physics and synthetic range sensing. It does not claim calibrated grasp/cutter/contact forces, physical sonar propagation, biological recovery, or real-world reliability. Current browser missions collect already detached, permitted loose fragments rather than cutting attached healthy colonies. Modal perception is remote GPU inference, not onboard hardware.

**Current live checkpoint: the first complete live browser placement is verified.** The independently inspected `output/video/final/full-episode.json` records actual Gemma responses in **2.687–3.201 s**, an actual Argon **RESCAN response in 22.700 s**, and a successful cuOpt/local-policy response in **689 ms**. An initially inconsistent source-colony observation held the mission; fresh evidence subsequently passed. A sensor dropout at **T+36.38** caused a local hold, and conditions recovered at **T+44.40**. The robot collected existing loose fragment **`donor-1-fragment-1` at T+65.083** and mechanically verified it on `recipient-1` at **T+80.55 simulated seconds**. Final metrics were **1 placement, 0 drops, 0 recoveries, 0 damage and 0 collisions**. See the [concise completed-placement trace](sim/pelagic/docs/evidence/live_stack_completed_placement.json).

This is a successful actual-model browser episode with uncertainty escalation and sensor hold/resume, not biological recovery or physical validation. **Live current-induced fragment-drop recovery remains unverified.** The run had no fragment drop and cannot demonstrate that case. The separate Isaac stream still uses its independent analytical controller, not this browser Gemma controller.

Earlier failures remain relevant evidence. The [saved fragment hold](sim/pelagic/docs/evidence/live_fragment_visibility_hold.json) accepted colony appearances but blocked pickup on unknown gripper state. Another actual **v13** uncertainty run received Argon **RESCAN twice, then HOLD**, followed by timeout and safe abort. Those runs demonstrate conservative holds; they are distinct from the later completed-placement episode and are not rewritten as successes. Appearance confidence remains uncalibrated, biological health unknown, and registered eligibility independent.

The camera prompt can use `observation.imageFocus` to identify the tracked target/gripper’s projected image coordinates. This is geometric guidance from known tracked positions, not a detector localization, proof of visibility, or a health/genet hint. All appearance, freshness, gripper, registry and local motion gates remain active. The assistance budget is volatile per gateway process: failures count, duplicate IDs reject, real episode resets create new IDs, and server restart clears the retained limits. This is a bounded demonstration API, not a durable account quota.

The [earlier safe-abort trace](sim/pelagic/docs/evidence/live_stack_safe_abort.json) records four unknown/zero-confidence frames and three retries under a superseded in-mission Argon planning architecture. It remains historical evidence of connected conservative behavior; it is not the v13 assistance trace and does not establish restoration success.

- [Setup, API, model and limits](sim/pelagic/docs/LIVE_LAB.md)
- [Full prioritized to-do list](sim/pelagic/docs/LIVE_DEMO_TODO.md)
- [Robot/base architecture and deployment](sim/pelagic/docs/ARCHITECTURE.md)
- [Reef composition and material response](sim/pelagic/docs/REEF_WORLD.md)
- [One-minute video and rubric plan](sim/pelagic/docs/ONE_MINUTE_DEMO.md)
- [Validation and reproducibility](sim/pelagic/docs/LIVE_LAB_VALIDATION.md)
- [Browser source](sim/pelagic/web/lab/)
- [Existing Isaac workflow](sim/README.md)

Run from `sim/pelagic`: `node --test tests/lab-*.test.mjs` and `python3 -m unittest discover -s tests -p test_lab_server.py -v`.

The coordinated checkpoint before shortcut removal passed **120 Node checks**, **38 Python backend checks**, and **11 live-stream/feed/finalizer checks** in separate suites; the removal changes require a new verification run. Mocked-model integration tests complete a loose-fragment mission and recovery, but do not establish live inference success. Browser QA verified evidence-source switching, recorded filters/selection, independent view pause, actual Isaac relay transport, earlier conservative holds/abort, and the subsequent actual-model completed browser placement. Live current-induced fragment-drop recovery remains unverified.

**Current capture policy:** production uses the model-guided mission only, with hold/rescan/abort on errors. The former Start presentation demo shortcut is removed. Any historical local/synthetic/2× recording retains that original provenance and cannot be relabelled as live inference or used to establish current model-guided recovery. Final PDF/video production remains with the deliverables workflow.
