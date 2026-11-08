# Reef Rescue AUV — interactive simulation lab

The browser lab preserves the project design system and uses the Reef Rescue AUV name. It is an editable case-presentation and controller-recovery environment alongside the Isaac simulator.

**Hosted demo:** https://reef-rescue-auv-lab.harrish-ayyanar.chatgpt.site (owner-private; scripted controller).

```sh
cd sim/pelagic
python3 scripts/run_lab.py
```

Open http://127.0.0.1:8090/lab/.

The lab includes scanned coral thickets, a sloping textured seabed, a connected gripper, fish/crab/turtle avoidance, two actual navigation routes, simulated sonar, editable colonies/obstacles, five fault types, recovery traces, and downloadable stress results. Inspect the exact robot-camera input from the telemetry panel. Choose Gemini only after setting `GEMINI_API_KEY` on the local server; simulation images and sonar telemetry are then sent to Google at decision gates. No key is shipped to the browser.

The browser engine is independent of the authoritative team mission/Isaac stack. It uses reduced physics and synthetic range sensing. It does not claim calibrated grasp/cutter/contact forces, physical sonar propagation, biological recovery, or real-world reliability. The Gemini endpoint is tested with mocked transport, not verified against a live account.

- [Setup, API, model and limits](sim/pelagic/docs/LIVE_LAB.md)
- [Validation and reproducibility](sim/pelagic/docs/LIVE_LAB_VALIDATION.md)
- [Browser source](sim/pelagic/web/lab/)
- [Existing Isaac workflow](sim/README.md)

Run from `sim/pelagic`: `node --test tests/lab-simulation.test.mjs tests/lab-worker.test.mjs` and `python3 -m unittest discover -s tests -p test_lab_server.py -v`.
