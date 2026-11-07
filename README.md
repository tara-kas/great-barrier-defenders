# Reef Rescue AUV

AgentVerse 2026, Robotics Track.

An autonomous underwater vehicle that locates loose, living coral fragments and re-attaches them to stable reef substrate. Built for reef restoration teams currently limited by diver depth, time, and weather, particularly on mesophotic reefs. Simulated in NVIDIA Isaac Sim.

Project notes and setup instructions are in the repository root.

## Models

| Role | Model |
|---|---|
| Lead reasoning (cloud) | gemini-4-argon |
| Managed sandbox | antigravity-preview-09-2026 |
| Deep research | deep-research-preview-04-2026 |
| Fast subagent | gemini-3.8-flash |
| Fast router | gemini-3.5-flash-lite |
| Live voice/vision | gemini-3.8-live |
| Image, high resolution | gemini-nano-banana-2.1 |
| Image, fast | gemini-3.1-flash-lite-image |
| On-device / edge | gemma-4-31b-it |

## How it works

Control and perception run on-device with no network dependency. A site optimiser scores and assigns reef locations for each fragment, and every placement is checked with a simulated current-push test; if a fragment shifts, the vehicle re-plans. Between dives, the cloud model reviews run logs, proposes patches, and runs them against a regression suite. A patch is only promoted after it passes and a human approves it.

## Repository layout

```
sim/         Isaac Sim world, vehicle, sensors, hydrodynamics
control/     Thrusters, station keeping, carry-aware control, safety limits
perception/  Classification and semantic mapping
agent/       On-device planning loop and site optimiser
cloud/       Debrief, patch generation, verification
dashboard/   Live telemetry: camera, detections, map, decision log
eval/        Scenario suite and regression harness
docs/        Technical summary and supporting assets
```

## Setup

See `SETUP.md` for environment setup and connecting to a remote Isaac Sim instance.