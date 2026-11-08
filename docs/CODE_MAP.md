# Code map

Start with [README](../README.md) for the mission, [ARCHITECTURE](ARCHITECTURE.md) for model authority and [SETUP](../SETUP.md) for runnable commands. This guide locates implementations and their checks; [EVIDENCE](EVIDENCE.md) indexes measured outcomes.

## Current browser pipeline

Paths below are relative to `sim/pelagic/`.

| File | Function |
| --- | --- |
| [web/lab/app.mjs](../sim/pelagic/web/lab/app.mjs) | Connects UI controls, camera captures, service readiness, perception/planning requests, bounded assistance and episode export. |
| [web/lab/simulation.mjs](../sim/pelagic/web/lab/simulation.mjs) | Runs the mission state machine and reduced physics; enforces visual freshness, registry eligibility, stock identity, safe motion, recovery and attachment checks. |
| [web/lab/scene.mjs](../sim/pelagic/web/lab/scene.mjs) | Builds the Three.js scene and camera views, fits inspection optics and projects tracked target geometry into captures. |
| [web/lab/terrain.mjs](../sim/pelagic/web/lab/terrain.mjs) | Supplies shared seabed geometry and contact helpers. |
| [web/lab/habitat.mjs](../sim/pelagic/web/lab/habitat.mjs), [habitat-regions.mjs](../sim/pelagic/web/lab/habitat-regions.mjs), [vehicle.mjs](../sim/pelagic/web/lab/vehicle.mjs) | Construct reef habitat, region layout and vehicle geometry. |
| [web/lab/mission-control.mjs](../sim/pelagic/web/lab/mission-control.mjs), [mission-panel.mjs](../sim/pelagic/web/lab/mission-panel.mjs) | Normalize browser/external mission records for a read-only evidence panel and render that panel. |
| [web/lab/semantic-memory.mjs](../sim/pelagic/web/lab/semantic-memory.mjs) | Retains bounded observations and contextual memory. Fresh handling permission remains in the controller's evidence checks. |
| [web/lab/telemetry.mjs](../sim/pelagic/web/lab/telemetry.mjs), [recorder.mjs](../sim/pelagic/web/lab/recorder.mjs) | Sample telemetry and record/export episodes. |
| [web/lab/index.html](../sim/pelagic/web/lab/index.html), [lab.css](../sim/pelagic/web/lab/lab.css) | Define the browser interface and styling. |
| [reefsim/lab_server.py](../sim/pelagic/reefsim/lab_server.py) | Hosts local HTTP routes; `ArchitectureAdapters` validates Gemma responses, requests cuOpt routes and handles Argon assistance/review. `local_mission_decision` applies the mission policy. |
| [scripts/run_lab.py](../sim/pelagic/scripts/run_lab.py) | Starts the local browser server and configured service adapters. |
| [scripts/modal_lab_backend.py](../sim/pelagic/scripts/modal_lab_backend.py) | Declares the authenticated Modal gateway and its Gemma/cuOpt GPU services. |
| [scripts/cuopt_route_adapter.py](../sim/pelagic/scripts/cuopt_route_adapter.py) | Converts declared route candidates into a native NVIDIA cuOpt solve and validates the selected route. |
| [sites/reef-lab/worker.mjs](../sim/pelagic/sites/reef-lab/worker.mjs) | Proxies browser requests to authenticated services using server-side credentials. |

For loose-stock handling, trace `app.mjs` → `ArchitectureAdapters` → `local_mission_decision` → `simulation.mjs`. Recipient and actual-fragment camera evidence meet independent source/recipient registry checks before motion is accepted. The attached-stock branch also inspects its donor colony.

## Configuration and edge entry points

| Location | Function |
| --- | --- |
| [.env.example](../.env.example) | Documents service endpoint, model, credential and deployment settings. |
| [compact recovery scene](../sim/pelagic/configs/reef_lab_compact_recovery.json), [scene guide](../sim/pelagic/configs/reef_lab_compact_recovery.md) | Define the compact mission geometry, registered detached stock, eligible recipient and mission settings. |
| [sim/pelagic/configs/](../sim/pelagic/configs/) | Holds other browser and simulator scene configurations. |
| [edge_serve.sh](../sim/pelagic/scripts/edge_serve.sh) | Starts pinned local Gemma serving with explicit container, cache, network and resource settings. |
| [edge_gateway.py](../sim/pelagic/scripts/edge_gateway.py) | Starts the edge gateway and checks local model identity and native solver readiness. |
| [edge_test_gateway.py](../sim/pelagic/scripts/edge_test_gateway.py) | Tests edge readiness contracts with controlled HTTP responses. |
| [edge_cuopt.Dockerfile](../sim/pelagic/scripts/edge_cuopt.Dockerfile), [edge_cuopt_server.py](../sim/pelagic/scripts/edge_cuopt_server.py) | Build and serve the local native cuOpt adapter. |
| [edge_benchmark.py](../sim/pelagic/scripts/edge_benchmark.py), [edge_capture_metadata.py](../sim/pelagic/scripts/edge_capture_metadata.py) | Record real image-inference responses, timing, resource measurements and runtime metadata. |
| [requirements.txt](../requirements.txt), [sim/pelagic/pyproject.toml](../sim/pelagic/pyproject.toml) | Declare root research dependencies and the simulator package. |

Use [EDGE_DEPLOYMENT](EDGE_DEPLOYMENT.md) for the pinned local deployment and evidence associated with each configuration.

## Isaac and Python research paths

| Location | Function |
| --- | --- |
| [reefsim/live_feed.py](../sim/pelagic/reefsim/live_feed.py), [scripts/push_isaac_feed.py](../sim/pelagic/scripts/push_isaac_feed.py) | Receive and relay the independent read-only Isaac camera/state feed. |
| [reefsim/isaac_scene.py](../sim/pelagic/reefsim/isaac_scene.py), [scripts/run_isaac.py](../sim/pelagic/scripts/run_isaac.py) | Build and launch the Isaac scene. |
| [reefsim/team_adapter.py](../sim/pelagic/reefsim/team_adapter.py), [team_physics.py](../sim/pelagic/reefsim/team_physics.py) | Connect the Python research mission to reduced simulation dynamics. |
| [agent/](../agent/README.md) | Implements the Python `MissionFSM`, source/recipient pairing, graft geometry, inventory, episodic memory and decision logging. `robot_interface.py` defines the adapter interface. |
| [mission/runner.py](../mission/runner.py) | Integrates research perception, the FSM and adapter-provided grip/placement checks; writes mission artifacts. |
| [perception/](../perception/README.md) | Provides model clients, detection/classification, image-to-world projection, registry updates, survey and experimental genet matching. |
| [perception/gemma_client.py](../perception/gemma_client.py), [gemini_client.py](../perception/gemini_client.py), [modal_vllm.py](../perception/modal_vllm.py) | Implement the research model clients and separate Gemma serving entry point. Their defaults are documented in [ARCHITECTURE](ARCHITECTURE.md#separate-python-research-components). |
| [cloud/debrief.py](../cloud/debrief.py) | Produces and validates standalone Argon debrief proposals and evidence citations. |
| [dashboard/](../dashboard/README.md) | Displays file-based research mission outputs through its local server. |
| [eval/](../eval/README.md) | Supplies mock adapters, seeded scenarios, integration regressions, synthetic fixtures and explicit model-evaluation commands. |
| [data/moore_reef/](../data/moore_reef/README.md) | Stores the research scenario's registry, inventory, frames and image crops. |
| [control/](../control/README.md) | Identifies where the implemented browser, research and simulation controllers live. |

## Verification and submission artifacts

| Location | What to check |
| --- | --- |
| [lab-simulation.test.mjs](../sim/pelagic/tests/lab-simulation.test.mjs) | Browser state transitions, handling permissions, provenance, safety, recovery and placement. |
| [lab-pipeline-contract.test.mjs](../sim/pelagic/tests/lab-pipeline-contract.test.mjs) | Browser/Python gateway contracts with controlled provider responses. |
| [lab-assistance.test.mjs](../sim/pelagic/tests/lab-assistance.test.mjs), [lab-camera.test.mjs](../sim/pelagic/tests/lab-camera.test.mjs), [lab-worker.test.mjs](../sim/pelagic/tests/lab-worker.test.mjs) | Assistance bounds and cancellation, real mesh/camera geometry and service-proxy behaviour. |
| [test_lab_server.py](../sim/pelagic/tests/test_lab_server.py), [test_cuopt_route_adapter.py](../sim/pelagic/tests/test_cuopt_route_adapter.py) | Provider validation, local policy, readiness, HTTP handling and solver-adapter contracts. |
| [sim/pelagic/tests/](../sim/pelagic/tests/) | Additional telemetry, memory, feed, optics, dynamics, geometry, linkage and contact regressions. |
| [agent/tests/](../agent/tests/), [perception/tests/](../perception/tests/), [eval/](../eval/) | Research planning, model parsing, geometry, mission integration and adapter checks. |
| [tools/verify_submission.py](../tools/verify_submission.py) | Verifies submission links, evidence hashes, run-index consistency and recorded edge benchmark metadata. |
| [tools/build_technical_summary.py](../tools/build_technical_summary.py) | Builds the current technical-summary PDF. |
| [docs/evidence/](evidence/), [docs/media/](media/README.md), [docs/submission/](submission/) | Preserve run exports, measurements, pipeline media and submitted/current PDFs. |
| [SCENARIOS](SCENARIOS.md), [JUDGING_GUIDE](JUDGING_GUIDE.md), [IMPLEMENTATION_STATUS](IMPLEMENTATION_STATUS.md) | Map acceptance cases, rubric questions and remaining implementation/validation work. |

Run the commands in [SETUP](../SETUP.md#regression-checks) for the relevant path. Raw run outcomes are recorded separately from regression results in [EVIDENCE](EVIDENCE.md).
