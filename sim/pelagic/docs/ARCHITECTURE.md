# Reef Rescue AUV: perception, telemetry and base-station planning

The lab now separates **Gemma visual perception**, **HTTP telemetry**, **Argon advisory reasoning**, **optional cuOpt candidate-route evaluation**, and the **local safety/controller loop**. Model and optimizer outages remain explicit. A configured endpoint is not proof of a deployed service, an on-robot runtime, or measured edge performance.

```text
Robot tool-camera JPEG ──► Gemma perception adapter ──► bounded observations
Local sonar/odometry ───────────────────────────────────────────┤
Known species/genet registry ── separate authoritative lookup ──┤
                                                             ▼
5 Hz local recorder ──► opt-in HTTP batches ──► base-station memory
                                                             │
                         optional cuOpt corridor costs ◄───────┤
                                                             ▼
                              Gemini 4 Argon / Interactions advice
                                                             │
                     local freshness, action and clearance verification
                                                             ▼
                          local controller / reflexes / mission outcome
```

Gemma estimates visible health; it does not infer lineage. Its numeric confidence is an **uncalibrated model score**, not measured classification accuracy. The perception prompt receives the image, active inspection target ID and phase; simulator health/genet truth is deliberately omitted. Unknown or failed perception cannot become an empty, safe seabed. Existing scripted synthetic sensing is labelled separately. The core motion/reflex implementation contains no network calls; a cloud plan cannot override local eligibility, freshness, route or outcome checks. Safety continuing during a remote outage is not equivalent to completing a mission without required perception.

## Runtime configuration

| Component | Environment | Actual scope |
| --- | --- | --- |
| Gemma | `GEMMA_BASE_URL` (OpenAI-compatible `/v1` base), `GEMMA_MODEL` (default `gemma-4-31b-it`), optional `GEMMA_API_KEY` | POSTs real camera pixels to `/chat/completions`; model name must match the server's served name. |
| Gemma location | `GEMMA_DEPLOYMENT=robot`, `base_station`, `modal`, or default `unverified` | Declared deployment metadata only; hardware locality and latency must be measured. A Modal endpoint is remote, never onboard. |
| Argon | `GEMINI_API_KEY` or `GOOGLE_API_KEY`; optional `ARGON_MODEL` (default **`gemini-4-argon`**) | Actual Google Interactions call, low thinking, 512 output-token bound, 25-second request timeout. No fallback model. |
| cuOpt | `CUOPT_ADAPTER_URL` (complete custom gateway `/solve` URL), optional `CUOPT_API_KEY`, `CUOPT_DEPLOYMENT` | Explicit custom gateway contract described below; not a claim that NVIDIA's native HTTP API accepts this payload. |
| Worker deployment | `LAB_ARCHITECTURE_BASE_URL`, optional `LAB_ARCHITECTURE_TOKEN` | Fixed HTTPS authenticated gateway forwarding these architecture endpoints to the Python backend. Without it, the Worker returns unconfigured statuses. It does not host GPU models. |

Run the local gateway with `python3 scripts/run_lab.py`. HTTP is permitted only for loopback adapter URLs; remote adapters require HTTPS. Credentials come from environment/runtime secrets and are never returned to the browser. No `.env` files are read by this lab gateway. The earlier `/api/lab/decision` endpoint remains a **separate legacy Gemini supervisory path**, with its own configured model; it is not relabelled Gemma or Argon.

## Endpoints and provenance

`GET /api/lab/architecture` reports `components.gemma`, `components.argon`, and `components.cuopt`: `configured`, `status`, `model`, `provider`, `deployment`, and `role`. Status starts `unconfigured` or `unverified`; only a valid actual provider reply changes it to `verified_response`. Failure changes it to `error`. Verification here proves a returned response passed the contract, not correct perception, robot residency, or closed-loop performance. The response also reports `localSafety.networkRequired:false` and telemetry receipts.

`POST /api/lab/perception` accepts `{id, observation, image}`. The image uses the existing bounded tool-camera JPEG contract (512 KiB decoded, maximum 768 pixels per side). Observation supplies an active `inspect_recipient`/`inspect_donor` phase and target/donor IDs. Response:

```json
{"id":"frame-1","requestId":"frame-1","frameTime":12.5,"source":"gemma","provider":"vllm_openai_compatible","model":"gemma-4-31b-it","deployment":"unverified","summary":"Actual provider text","uncertainty":"Actual provider text","observations":[{"id":"recipient-1","health":"unknown","confidence":0}],"confidenceMeaning":"uncalibrated_model_score"}
```

This is a **schema illustration**, not a saved inference result. Replies also contain measured request latency and the SHA-256/time/dimensions of the actual JPEG. Valid health values are `healthy`, `bleached_alive`, `dead`, `unknown`; only the requested visible target ID is accepted. Missing target observations, foreign IDs and invalid scores reject the response. No health or genet ground-truth labels are supplied to the classifier prompt.

`POST /api/lab/plan` accepts `{id, observation, allowedActions, perception?}`. `observation.time` (or `frameTime`) is required and checked **before** any paid request. Perception may be the raw Gemma packet or the engine's bounded onboard wrapper. The request preserves sonar/fusion source labels, registry facts and declared route alternatives. Argon returns `decision`, `reason` and optional `routeMode` restricted to declared `direct`/`clearance` alternatives. The gateway adds `requestId`, `frameTime`, `source:"argon"`, provider/model/deployment, token usage and actual latency. `optimizer.source:"not_configured"` explicitly marks absent cuOpt. Configured cuOpt failure stops that plan rather than relabelling a local path as GPU optimized. The engine must ingest/verify the plan before applying it; there is no arbitrary model-generated actuator command.

`POST /api/lab/telemetry` accepts `{streamId, sequence, frames}`: one to five actual recorder frames, at most one batch per second and 64 KiB total. The UI uses 1.1-second, non-overlapping sends. Receipt fields are `{streamId, sequence, acceptedFrames, totalFrames, lastFrameTime, retainedFrames}`. Duplicate/out-of-order sequences or simulation times are rejected; a reset starts a new stream ID. The server keeps a **300-frame volatile ring**, at most 16 stream cursors, receipt count and last-receipt age. There are no model calls, image bytes, credential fields or persistent logs in this path. Disconnect stops uploads. This is a functioning HTTP demo uplink, **not an acoustic network model**. It does not yet provide a database, multi-user telemetry broker or replay service.

## Optional GPU deployment and cuOpt scope

The team already has `great-barrier-defenders/perception/modal_vllm.py`; reuse that deployment rather than creating a second untracked Gemma service. It has not been deployed by this change. Before an account owner deploys, confirm Gemma license acceptance, Hugging Face access, exact repository revision, vLLM support, GPU memory and a protected endpoint. The existing scaffold's Hugging Face repository spelling is marked unverified; current official names include `google/gemma-4-31B-it`, `google/gemma-4-E2B-it`, and `google/gemma-4-E4B-it`. Set its supported `GEMMA_HF_REPO` override deliberately and keep the lab's served-model name consistent. Edge-size existence is not evidence this application fits an edge device. Modal credentials and endpoint bearer secrets stay in the account owner's secret store. No Modal resources or credits were provisioned.

`scripts/cuopt_route_adapter.py` is an **optional, undeployed GPU scaffold**. On a compatible GPU environment with NVIDIA cuOpt 26.10, cudf and NumPy, it converts each declared corridor to a weighted waypoint graph, uses `WaypointMatrix` and the cuOpt routing solver to evaluate source-to-target cost, and returns the least-cost declared corridor. It is syntax checked but has not executed against a GPU in this workspace. It does not create new free-space paths or perform local dynamic avoidance. Costs currently represent geometric route length; terrain/dynamic safety remains a local check. A proper deployment must test infeasible problems, pinned library/container versions and solver outcomes before reporting cuOpt performance. The scaffold binds loopback port 8091 and requires `CUOPT_API_KEY`; expose it remotely only through an authenticated HTTPS gateway. It can be packaged in an owner-provisioned Modal GPU service, but no Modal cuOpt deployment is claimed here.

Custom optimizer request: `{id, alternatives:[{id,points}], fusion, currentVector}`. Response must include matching `id`, `source:"cuopt"`, declared `routeMode`, bounded `costs`, and optional solver metadata. The native NVIDIA service uses its own versioned request schemas; point `CUOPT_ADAPTER_URL` at this adapter, not blindly at `/cuopt/request`.

## Verification and remaining deployment work

On November 8, 2026, the primary agent completed an **actual Argon planning-stage call** with a seed-42 engine approval observation at simulation time 21.4 s: approximately 26.6 KiB of synthetic sonar/UV/registry telemetry, no Gemma result and no camera image. The call returned `proceed` with the declared `clearance` route in **16,693 ms**. Its reason explicitly acknowledged the missing camera. No interaction ID was present in that provider response; the gateway preserves null rather than inventing one. cuOpt was explicitly unconfigured. This verifies the Argon transport/planning stage only, **not** the complete Gemma → telemetry → Argon → cuOpt closed loop or onboard perception.

Tests exercise actual request construction and strict failure handling using mocked Gemma/cuOpt/provider transports, plus real loopback HTTP. A model mock is test evidence, not a live-model demonstration. Remaining steps: provision a real Gemma endpoint; verify camera-target association and classification against positive/negative controls; measure hardware/model latency; deploy/test the cuOpt GPU scaffold; complete a live end-to-end episode; and test link loss while local safety remains active.

Official references checked November 8, 2026: [Gemma vision and model examples](https://ai.google.dev/gemma/docs/capabilities/vision/image), [Gemma model overview](https://ai.google.dev/gemma/docs/core), [Gemini 4 Argon for robotics](https://developers.googleblog.com/gemini-4-argon-for-robotics/), [Interactions API](https://ai.google.dev/gemini-api/docs/interactions-overview), [cuOpt robot waypoint-routing examples](https://docs.nvidia.com/cuopt/user-guide/latest/cuopt-python/routing/routing-examples.html), [cuOpt local-avoidance distinction](https://docs.nvidia.com/cuopt/service/latest/faq.html), [Modal Gemma/vLLM example](https://modal.com/docs/examples/vllm_inference), and [Modal secrets](https://modal.com/docs/guide/secrets).
