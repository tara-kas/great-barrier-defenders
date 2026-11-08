# Reef Rescue AUV

AgentVerse 2026, Robotics Track.

An autonomous underwater vehicle that treats bleached coral. Healthy coral can restore a bleached fragment of the same genet through direct contact, by transferring symbionts ([Collins et al. 2026](https://doi.org/10.1126/sciadv.aeh1580)). This vehicle makes that contact at reef scale, for restoration teams limited by diver depth, time and weather. It is simulated in NVIDIA Isaac Sim, in a Moore Reef scenario on the Great Barrier Reef.

Project notes and setup instructions are in the repository root.

## Models

| Role | Model | Status |
|---|---|---|
| Between-dives debrief | `gemini-4-argon` | In use, `cloud/debrief.py` |
| Coral detection and classification | `gemma-4-31b-it`, self-hosted | Built, `perception/` |
| Synthetic test images | `gemini-nano-banana-2.1` | In use, `eval/generate_synthetic_frames.py` |

## How it works

During a dive, the mission loop surveys the seabed and classifies each colony with Gemma. For bleached colonies it reads UV fluorescence to identify the genet, then collects a healthy fragment of that genet from a base station and places it touching the colony. Dead colonies are skipped, and so is any colony without a confident in-stock genet match, because contact with the wrong genet harms the coral. The loop makes no cloud calls, and Gemma runs on the same machine as the vehicle's stack. If perception fails repeatedly the mission aborts rather than finishing with an empty map.

The fragment stays in contact. The vehicle returns at day 7 to confirm contact and at day 56 to judge recovery.

Every decision is logged with the evidence behind it. `mission/` connects these parts and writes live files for the dashboard.

## Verification loop

Two checks are built today:

1. **In the dive:** the mission will not start without a post-placement push test, which must confirm the fragment held and stayed in contact. If not, the colony stays open and the vehicle retries, then gives up on it after three attempts. The test itself comes from the simulator, which is still to be connected.
2. **After the dive:** `gemini-4-argon` reviews the decision log and flags suspect transitions. Every flag must cite log values, and code checks each citation against the log. Argon proposes one patch, which a person reviews.

Not built yet: applying proposed patches automatically, or running them against the regression suite before a person approves them.

## Repository layout

```
sim/         Isaac Sim world, vehicle, sensors, hydrodynamics
control/     Thrusters, station keeping, carry-aware control, safety limits
perception/  Classification and semantic mapping
agent/       On-device mission FSM, pairing and graft-point selection
mission/     Entry point connecting perception, the FSM and the dashboard
cloud/       Between-dives Argon debrief
dashboard/   Live telemetry: camera, detections, map, decision log
eval/        Scenario suite and regression harness
docs/        Technical summary and supporting assets
```

## Setup

See `SETUP.md` for environment setup and connecting to a remote Isaac Sim instance.

## Interactive browser lab

The [Reef Rescue AUV live demo](LIVE_DEMO.md) adds an editable Three.js reef, fault recovery, wildlife avoidance, two navigation routes, simulated sonar, and optional Gemini camera review. It preserves the existing design system. Run `python3 sim/pelagic/scripts/run_lab.py` or open the private hosted demo linked in the guide. Browser physics and sensor models are explicitly separate from Isaac validation.

## Isaac Sim checkpoint

The `simulation` branch includes the offline DGX Spark simulator, bundled assets, configurations and tests under [`sim/pelagic/`](sim/pelagic/README.md). Start with [`sim/README.md`](sim/README.md) for the connected team mission, natural live-reef harvesting, same-fragment recovery, push testing and offline recording commands. The default recording uses an explicitly labelled pre-mapped perception demo; optional Gemini inference requires separate cloud opt-in.
