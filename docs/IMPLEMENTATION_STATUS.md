# Mission operating reference

## Runtime components

The browser mission in `sim/pelagic` combines the tool camera, Gemma visual assessment, an independent stock registry, local policy, native cuOpt routing and local motion/attachment checks. Argon provides contextual advice and visual checks during a held issue. The [file guide](CODE_MAP.md) maps these functions to their implementations.

| Service | Configuration | Readiness signal |
| --- | --- | --- |
| Gemma | `GEMMA_BASE_URL`, `GEMMA_MODEL`, optional `GEMMA_API_KEY` | The model service reports the configured served model ID. |
| Native cuOpt | `CUOPT_ADAPTER_URL`, `CUOPT_API_KEY` | A native readiness solve returns a valid route result. |
| Argon | `GEMINI_API_KEY`, `ARGON_MODEL` | The gateway reports configuration; assistance responses carry provider and interaction metadata. |
| Browser gateway | Local server or authenticated Modal gateway/Worker | Architecture health reports service state; the UI enables mission start when required services are ready. |

Use [SETUP](../SETUP.md) for environment configuration, [hosted deployment](../sim/pelagic/docs/ARCHITECTURE.md#integrated-authenticated-modal-deployment) for Modal, or [Spark deployment](EDGE_DEPLOYMENT.md) for local GPU services. Keep credentials on the gateway host.

## Execute a mission

1. Start the configured gateway and open the lab.
2. Load the [compact scene](../sim/pelagic/configs/reef_lab_compact_recovery.json) using **Environment builder → Import JSON**.
3. Select **Robot + base** and wait for service readiness.
4. Start the mission. The controller selects compatible stock and inspects the recipient and actual detached fragment.
5. Gemma returns target-bound appearance and gripper evidence. The gateway checks the registry and requests a native cuOpt route.
6. The local controller collects, transports and places the fragment, then verifies mechanical attachment.
7. Use **Export** to save the episode and transport activity. Review request IDs, image hashes, model/solver receipts and final counters using [EVIDENCE](EVIDENCE.md).

## Assistance and service behavior

An uncertain image or disturbance holds mission progression while local safety physics continues. Argon receives structured telemetry and observations and returns `rescan`, `hold` or `abort`, with bounded contextual guidance. A rescan obtains a new image; the next matching Gemma request can consume the advisory context once. Episode, target, capture and expiry checks keep the advice tied to its intended observation.

Assistance permits three attempts per episode. The gateway uses a 25-second socket timeout; this applies to blocking socket operations rather than a total request wall-clock deadline. The browser bounds its request wait and the controller aborts after 90 active simulated seconds of assistance hold. An occupied gateway request slot rejects concurrent model requests. Episode budgets are process-local and reset when the gateway restarts.

For service errors, inspect the fixed diagnostic code, retryability and HTTP status in the response. Check the configured endpoint, served model ID and provider health before starting another episode. Restart services between episodes, then repeat readiness checks. The [scenario guide](SCENARIOS.md) describes current, visibility, camera, grip and placement controls.

## Run software checks

Follow the [regression commands](../SETUP.md#regression-checks) for the browser/controller and gateway. Run `python3 tools/verify_submission.py` from the repository root to check artifact hashes, model identities and documentation links. The separate Python research stack has its own commands in [SETUP](../SETUP.md#separate-python-research-stack).
