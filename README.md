# Reef Rescue AUV

AgentVerse 2026, Robotics Track.

An autonomous underwater vehicle that locates loose, living coral fragments and re-attaches them to stable reef substrate. Built for reef restoration teams currently limited by diver depth, time, and weather, particularly on mesophotic reefs. Simulated in NVIDIA Isaac Sim.

Project notes and setup instructions are in the repository root.

## Models

| Role | Model | Status |
|---|---|---|
| Between-dives debrief | `gemini-4-argon` | In use, `cloud/debrief.py` |
| Coral detection and classification | `gemma-4-31b-it`, self-hosted | Built, `perception/` |
| Synthetic test images | `gemini-nano-banana-2.1` | In use, `eval/generate_synthetic_frames.py` |

## How it works

During a dive, a six-state mission loop surveys the seabed, classifies coral with Gemma, pairs donors with recipients using an inspectable cost function, picks a graft point from the depth data, and places the fragment. The loop makes no cloud calls, and Gemma runs on the same machine as the vehicle's stack. If perception fails repeatedly the mission aborts rather than finishing with an empty map.

Every decision is logged with the evidence behind it. `mission/` connects these parts and writes live files for the dashboard.

## Verification loop

Two checks are built today:

1. **In the dive:** the mission will not start without a post-placement push test. If a fragment shifts, the site stays open and the vehicle retries, then gives up on that site after three attempts. The test itself comes from the simulator, which is still to be connected.
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