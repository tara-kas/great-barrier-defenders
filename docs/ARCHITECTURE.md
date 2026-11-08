# Architecture and model source map

## Current mission runtime

The browser captures the rendered robot tool camera, sends the image through the authenticated gateway and applies returned visual packets only after target, capture, ordering and freshness checks. Registry eligibility is independent of visual appearance. Local policy proposes handling only after both inputs agree; native cuOpt selects a candidate route; the browser validates the proposal against local geometry and safety constraints.

| Responsibility | Source |
| --- | --- |
| Browser capture, model calls, uncertainty escalation and review | [app.mjs](../sim/pelagic/web/lab/app.mjs) |
| Mission state machine, physics, evidence gates and identity | [simulation.mjs](../sim/pelagic/web/lab/simulation.mjs) |
| Gemma image request, local policy, cuOpt adapter, Argon assistance/review | [lab_server.py](../sim/pelagic/reefsim/lab_server.py), `ArchitectureAdapters` |
| Gemma vLLM and native cuOpt serving | [modal_lab_backend.py](../sim/pelagic/scripts/modal_lab_backend.py) |
| Same-origin authenticated service proxy | [worker.mjs](../sim/pelagic/sites/reef-lab/worker.mjs) |
| Scenario data and registry | [compact scene](../sim/pelagic/configs/reef_lab_compact_recovery.json) |
| Bounded remembered observations | [semantic-memory.mjs](../sim/pelagic/web/lab/semantic-memory.mjs) |
| Episode capture and export | [recorder.mjs](../sim/pelagic/web/lab/recorder.mjs) |

Gemma's active served ID is `gemma-4-E4B-it` with weights `google/gemma-4-E4B-it`. Its `appearance/v1` output describes visible appearance, object kind and fragment/gripper state. It does not establish health, genetic compatibility or ecological suitability.

Normal decisions use `reef-local-policy-v1` plus cuOpt. Gemini `gemini-4-argon` receives structured observations for a held issue and may return only `rescan`, `hold` or `abort`. Assistance has a 25-second request timeout and a three-attempt per-episode budget; the gateway's in-memory accounting retains up to 64 episodes. This is process-local accounting, not a durable distributed quota. The assistance operation does not include the JPEG. Optional post-mission review consumes episode/activity data and generates recommendations; it does not automatically patch or deploy code.

Failures remain explicit. Remote services cannot bypass local clearance, current, grip, fragment identity or mechanical attachment verification. External coordinates are not executed as arbitrary actuator commands.

## Deployment and simulator boundaries

The measured demonstration uses **remote Modal Gemma and cuOpt**, Google-hosted Argon and local browser safety/physics. Model endpoints and secrets are configured server-side. The deployment declares L4/A10 choices for Gemma and T4 for cuOpt; no measured on-robot compute budget is claimed.

An independent Isaac RTX camera/state feed is exposed by [live_feed.py](../sim/pelagic/reefsim/live_feed.py) and the bridge/push scripts. It is a read-only visualization channel. It is not the browser mission's contact physics or actuator execution engine. See the detailed [Pelagic architecture](../sim/pelagic/docs/ARCHITECTURE.md) and [simulation overview](../sim/README.md).

## Separate Python research components

| Component | Role and model |
| --- | --- |
| [agent](../agent/README.md), [mission](../mission/README.md) | Python FSM, planning and adapter-based mission research. |
| [perception/gemma_client.py](../perception/gemma_client.py) | OpenAI-compatible client, default `gemma-4-31b-it`; deployment depends on configured URL. |
| [perception/gemini_client.py](../perception/gemini_client.py) | Optional cloud perception using `gemini-3.5-flash-lite`. |
| [cloud/debrief.py](../cloud/debrief.py) | Standalone `gemini-4-argon` log debrief with citation/proposal validation. |
| [eval/generate_synthetic_frames.py](../eval/generate_synthetic_frames.py) | Optional fixture generation with `gemini-nano-banana-2.1`. |
| [control](../control/README.md) | Reserved package; the working controllers live in the paths above. |

These components are useful development paths, but importing them is not evidence that they ran in the saved browser episode. [EVIDENCE](EVIDENCE.md) identifies the actual run, models and outcome.
