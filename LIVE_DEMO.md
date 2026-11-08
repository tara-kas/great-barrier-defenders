# Reef Rescue AUV — interactive simulation lab

The browser lab preserves the project design system and uses the Reef Rescue AUV name. It is an editable case-presentation and controller-recovery environment alongside the Isaac simulator.

**Hosted demo:** https://reef-rescue-auv-lab.harrish-ayyanar.chatgpt.site (owner-private; scripted controller).

```sh
cd sim/pelagic
python3 scripts/run_lab.py
```

Open http://127.0.0.1:8090/lab/.

The lab includes manual robot piloting, seeded healthy/bleached reef regions with mixed transitions, visible continuous current vectors, UV exposure gates, current-load grip loss and same-fragment recovery, scanned coral thickets, a sloping textured seabed, a connected gripper, fish/crab/turtle avoidance, two actual navigation routes, simulated sonar, editable colonies/obstacles, five fault types, recovery traces, and downloadable stress results. Inspect the exact robot-camera input from the telemetry panel. The Robot & base panel separates Gemma camera perception, the telemetry uplink, Gemini Argon reasoning and optional NVIDIA cuOpt route optimization. Configure the local server adapters before selecting that policy. The legacy cloud-Gemini controller remains a separate mode. No key is shipped to the browser.

The browser engine is independent of the authoritative team mission/Isaac stack. It uses reduced physics and synthetic range sensing. It does not claim calibrated grasp/cutter/contact forces, physical sonar propagation, biological recovery, or real-world reliability. A live Argon planning call on actual simulation telemetry returned a bounded proceed/clearance decision in 16.7 seconds. Onboard Gemma, a live cuOpt solve and the full connected loop remain unverified.

- [Setup, API, model and limits](sim/pelagic/docs/LIVE_LAB.md)
- [Full prioritized to-do list](sim/pelagic/docs/LIVE_DEMO_TODO.md)
- [Robot/base architecture and deployment](sim/pelagic/docs/ARCHITECTURE.md)
- [Reef composition and material response](sim/pelagic/docs/REEF_WORLD.md)
- [One-minute video and rubric plan](sim/pelagic/docs/ONE_MINUTE_DEMO.md)
- [Validation and reproducibility](sim/pelagic/docs/LIVE_LAB_VALIDATION.md)
- [Browser source](sim/pelagic/web/lab/)
- [Existing Isaac workflow](sim/README.md)

Run from `sim/pelagic`: `node --test tests/lab-simulation.test.mjs tests/lab-worker.test.mjs tests/lab-telemetry.test.mjs` and `python3 -m unittest discover -s tests -p test_lab_server.py -v`.
