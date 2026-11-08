# Reef Rescue interactive lab

The browser lab runs the registered loose-fragment mission with Gemma camera perception, local policy, native cuOpt routing and Argon assistance. The [pipeline video](docs/media/pipeline-video.mp4) and [system overview](README.md) introduce the workflow.

## Start the lab

From the repository root:

```bash
python3 sim/pelagic/scripts/run_lab.py
```

Open [the local lab](http://127.0.0.1:8090/lab/). Configure model services using [SETUP](SETUP.md) before starting a model-guided mission. The [hosted lab](https://reef-rescue-auv-lab.harrish-ayyanar.chatgpt.site/lab/) uses an authenticated Modal gateway and may require owner access.

1. Open **Environment builder** and import `sim/pelagic/configs/reef_lab_compact_recovery.json`.
2. Select **Robot + base**, wait for Gemma and cuOpt readiness, then start the mission.
3. Watch recipient and detached-fragment inspection, route selection, collection, transport and mechanical placement verification.
4. Use the tool-camera view and activity log to inspect captures, provider responses and route decisions.
5. Use **Export** to save the episode and transport activity.

## Models and decisions

- **Gemma `gemma-4-E4B-it`** evaluates fresh tool-camera images and reports appearance, visibility and gripper state.
- **Local policy `reef-local-policy-v1`** combines validated visual evidence with independent registry eligibility.
- **Native NVIDIA cuOpt** selects among declared route candidates.
- **Gemini `gemini-4-argon`** supplies bounded contextual advice and visual checks during held issues. Its advice accompanies a fresh matching Gemma assessment.
- **Local control** enforces identity, freshness, clearance, current, grip and attachment checks.

The browser owns its reduced physics and mission state. The **Mission evidence** workspace can also display an independent read-only Isaac/team source. The source selector and exported metadata identify which implementation produced each record.

## Controls and reference

Pause before editing a scene. **Current surge** and **Sensor dropout** act immediately; **Drop fragment** and **Bad placement** queue a disturbance for its applicable stage. Manual **Pilot** controls are separate from autonomous mode. A reset creates a new episode.

- [Lab operation and API reference](sim/pelagic/docs/LIVE_LAB.md)
- [Architecture and hosted deployment](sim/pelagic/docs/ARCHITECTURE.md)
- [Scenario controls and regression cases](docs/SCENARIOS.md)
- [Selected result artifacts](docs/EVIDENCE.md)
- [File guide](docs/CODE_MAP.md)
- [Spark deployment](docs/EDGE_DEPLOYMENT.md)
