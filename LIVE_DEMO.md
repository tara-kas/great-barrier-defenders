# Reef Rescue AUV — interactive simulation lab

The browser lab preserves the project design system and uses the Reef Rescue AUV name. It is an editable case-presentation and controller-recovery environment alongside the Isaac simulator.

**Hosted demo:** https://reef-rescue-auv-lab.harrish-ayyanar.chatgpt.site (owner-private; model-guided autonomy with explicit local fallback).

```sh
cd sim/pelagic
python3 scripts/run_lab.py
```

Open http://127.0.0.1:8090/lab/.

The lab includes manual robot piloting, seeded healthy/bleached reef regions with mixed transitions, visible continuous current vectors, UV exposure gates, current-load grip loss and same-fragment recovery, scanned coral thickets, a sloping textured seabed, a connected gripper, fish/crab/turtle avoidance, two actual navigation routes, simulated sonar, editable colonies/obstacles, five fault types, recovery traces, and downloadable stress results. Use the live tool/forward camera PiP and enlarge it to inspect the robot view. Brighter white and UV lamps illuminate real rendered frames. Model sends/replies, timings and route decisions appear in the activity log; scene-specific semantic memory can be saved and exported. The Robot & base panel separates Gemma camera perception, the telemetry uplink, Gemini Argon reasoning and NVIDIA cuOpt route optimization (required in full-stack mode). The hosted Worker connects to the private Modal Gemma/cuOpt gateway and Gemini Argon; local deployments use the documented adapters. The UI automatically checks the model stack and surfaces local fallback only when services are unavailable. No key is shipped to the browser.

## Aryan’s mission evidence, embedded

The **Mission evidence** workspace brings the registry map, health filters, linked colony selection, stable historical decision inspection, evidence/outcome details and independent view pause from Aryan Patel’s dashboard into the lab design. His original dashboard and commits are preserved unchanged. The bridge reuses `dashboard/server.py` readers rather than introducing a competing parser.

Choose **Lab simulation**, **Live team mission · read only**, or **Recorded team mission**. The bundled recorded team run contains 24 colonies, 10 decisions, one dislodgement and one mechanically treated recipient; it is explicitly labelled reduced-physics, synthetic premapped evidence, with no camera frame. It is not a live Gemma success. Live files can be connected with `python3 scripts/run_lab.py --team-run-dir /absolute/path/to/mission-output`; the hosted deployment currently has no live Isaac feed configured. The read-only source never commands the browser robot.

The browser engine is independent of the authoritative team mission/Isaac stack. It uses reduced physics and synthetic range sensing. It does not claim calibrated grasp/cutter/contact forces, physical sonar propagation, biological recovery, or real-world reliability. A live Argon planning call on actual simulation telemetry returned a bounded proceed/clearance decision in 16.7 seconds. A live NVIDIA cuOpt GPU solve has also succeeded. The complete live uncertainty-handling chain has now been verified: four actual Gemma camera observations remained unknown/zero-confidence; cuOpt solved the route options and Argon requested three fresh inspections followed by a safe abort at 100.43 simulated seconds. No coral was harvested or placed. This validates connected inference and bounded safety behavior, not accepted health classification or a successful restoration/recovery. See [the actual trace](sim/pelagic/docs/evidence/live_stack_safe_abort.json). Modal perception is remote, not onboard hardware.

- [Setup, API, model and limits](sim/pelagic/docs/LIVE_LAB.md)
- [Full prioritized to-do list](sim/pelagic/docs/LIVE_DEMO_TODO.md)
- [Robot/base architecture and deployment](sim/pelagic/docs/ARCHITECTURE.md)
- [Reef composition and material response](sim/pelagic/docs/REEF_WORLD.md)
- [One-minute video and rubric plan](sim/pelagic/docs/ONE_MINUTE_DEMO.md)
- [Validation and reproducibility](sim/pelagic/docs/LIVE_LAB_VALIDATION.md)
- [Browser source](sim/pelagic/web/lab/)
- [Existing Isaac workflow](sim/README.md)

Run from `sim/pelagic`: `node --test tests/lab-*.test.mjs` and `python3 -m unittest discover -s tests -p test_lab_server.py -v`.

The integrated release passes **146 automated checks** (99 Node, 29 Python lab/API, 4 cuOpt protocol, 12 team-feed bridge and 2 original dashboard tests). Browser QA also verified source switching, recorded filters and selection, decision evidence, independent view pause and the actual connected safety episode.
