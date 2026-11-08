# Reef Rescue AUV live reef lab

Run the editable browser demonstration from the repository root:

```sh
python3 scripts/run_lab.py
```

Open **http://127.0.0.1:8090/lab/**. Python 3.10+ and a browser with WebGL2 are required. Three.js and reef assets are bundled; scripted control needs no cloud API, npm installation, Isaac runtime, or network download. The existing Isaac console and recorded demonstrations are unchanged.

The browser lab owns a separate deterministic simulation. Its selectable cameras, scene editor, water controls, failure injection, event trail and outcome metrics expose an engineering demonstration of the restoration lifecycle. Pause before editing colonies and obstacles. Export scenes to retain configurations; reset creates a fresh episode. Dropped fragments, rejected cuts and failed placement must be handled before a placement can count as successful. The mission retains registered species/genet eligibility and never presents dead coral as a living recipient.

## Robot perception and base-station planning

The current requested architecture separates Gemma camera perception from Gemini Argon mission reasoning and NVIDIA cuOpt route optimization. Local execution retains collision avoidance, grip/clearance limits and stale-response checks. See [the architecture guide](ARCHITECTURE.md) for endpoint configuration, provenance and the optional Modal deployment path. Gemma hosted on Modal is remote perception; an onboard claim requires a local runtime and measurements on the intended device.

The [complete backlog](LIVE_DEMO_TODO.md) retains every scene, physics, optics, memory and judging requirement. The [one-minute plan](ONE_MINUTE_DEMO.md) maps visible evidence to the five judging criteria.

## Legacy Gemini supervisory mode

Provide `GEMINI_API_KEY` or `GOOGLE_API_KEY` in the **server's environment**, then restart the server. Optional `GEMINI_MODEL` selects a different compatible Gemini model; the default is `gemini-3.5-flash-lite`. The browser never receives the key. Selecting Gemini deliberately enables remote decisions: **the rendered robot tool-camera image and structured sonar/mission telemetry are sent to Google**. The camera image is captured separately from the spectator view. This is a multimodal supervisory controller; it is not a continuous low-level VLM motion policy.

At inspection and recovery gates, the browser supplies a decision ID, observation, camera frame and permissible high-level choices. Gemini receives the frame as an actual image input, not as a description substituted for pixels. It can inspect visible gripper alignment, fragments and contact, and compare those observations with simulated sonar ranges. Gemini returns `proceed`, `retry` or `abort` plus a reason. Registered species/genet/health records remain authoritative; image colour cannot establish health or genetic compatibility. The deterministic engine still owns eligibility, motion, fragment conservation and outcome checks. Model responses cannot inject coordinates or arbitrary commands. The browser must match the pending decision ID before applying the reply.

Requests use Google's [Interactions API](https://ai.google.dev/gemini-api/docs/interactions-overview), [inline image input](https://ai.google.dev/gemini-api/docs/image-understanding), [structured JSON output](https://ai.google.dev/gemini-api/docs/structured-output) and the documented [Gemini 3.5 Flash-Lite model](https://ai.google.dev/gemini-api/docs/models/gemini-3.5-flash-lite), checked November 8, 2026. Requests specify `store: false`, `stream: false`, minimal thinking and 512 maximum output tokens. `store: false` controls retrievable interaction history, not all provider data policies. There is one request in flight, a 25-second socket timeout, a one-second minimum interval, a 30-request/minute process limit, and no application retry. A socket timeout is not a strict total-operation deadline. The optional Worker uses the same contract with a 25-second fetch abort and per-isolate limits; those limits are not global account quotas.

Missing keys, unavailable models, rate limits, invalid output and network errors are visible errors. They do not substitute a scripted decision or another model. Resume with an explicit retry or deliberately switch to scripted control. Merely configuring a key does not establish that the key, billing or model access works. Tests use a mock provider transport; live provider access requires a real successful call.

## HTTP contract

`GET /api/lab/health` returns `{ok, geminiConfigured, model, controller, input:"robot_camera_and_sonar_telemetry"}`. Configured only means a nonempty server-side key is present.

`POST /api/lab/decision` accepts JSON:

```json
{"id":"decision-1","observation":{"phase":"inspect","eligible":true,"sonar":{"valid":true,"ranges":[0.5,1.2]}},"allowedActions":["proceed","abort"],"image":{"mimeType":"image/jpeg","data":"BASE64_JPEG_BYTES","camera":"tool","time":12.5}}
```

`image` is optional for API compatibility. A call without it is explicitly reported as `inputMode:"structured_telemetry"` and cannot count as a camera-reviewed decision. JPEG data must be canonical raw base64, not a data URL; the image must be from `camera:"tool"`, with a finite nonnegative simulation timestamp. The limits are 512 KiB decoded image bytes, 768 pixels on each side, 32 KiB structured telemetry independently, and 800 KiB total HTTP body. The standard-library parser validates JPEG framing and SOF dimensions without decoding pixel entropy; the provider must still accept the encoded image. This avoids an extra imaging dependency.

A successful response contains `{id, decision, reason, routeMode, source:"gemini", model, latencyMs, interactionId, usage}` plus `inputMode`, `inputImageSha256`, `inputCamera`, `inputImageTime`, `inputImageWidth` and `inputImageHeight`. `routeMode` is `direct`, `clearance` or null. A non-null route must be explicitly declared in the request's `observation.route.alternatives` (or `observation.navigation.alternatives`) using `id` or `mode`. Missing route suggestions are returned as null for older clients. The model compares the supplied candidate routes with fused sonar hazards and camera evidence; a route suggestion cannot bypass an inspection/recovery decision gate. Invalid or undeclared routes reject the entire reply. Reasons are requested to cite the actual inputs; this validation does not establish that the model's reasoning is correct or calibrated.

The image evidence records exactly which input bytes were sent; image fields are null for telemetry-only calls. The hash proves input identity, not correct visual reasoning. Invalid requests return 400, cross-origin requests 403, unsupported content types 415, rate/concurrency limits 429, provider failures 502, and missing credentials 503. Errors contain `{ok:false,error}`. Responses never include API keys, image bytes or provider error bodies.

The default host is loopback. This development server is not a multi-user deployment backend. If deployed beyond the local machine, use an authenticated application gateway with per-user quotas and a server-side secret store. Static hosting can run scripted browser mode; Gemini needs this API or an equivalent protected backend. The local server only serves `web/` and `assets/`; repository internals and directory listings are excluded.

## Manual, randomized and mixed environments

Manual pilot commands, seeded scene randomization, mixed coral/rock topology, variable current vectors and moving schools can be inspected through the same browser simulation state. Manual motion and autonomous mission control are distinct pilot modes; recorded pilot mode and input-watchdog status identify who supplied motion commands. Randomized scenes remain subject to eligibility and collision/clearance checks. A chosen seed only makes the seeded scene reproducible; it does not reproduce an unrecorded sequence of human input or Gemini responses.

The browser's `TelemetryRecorder` samples supplied snapshots at up to **5 Hz of simulation time**, retaining at most **3,000 frames** (approximately ten minutes at that rate). It does not interpolate missing samples or invent measurements. The stream records pose/velocity, pilot state, current vector, applied force components, closest sonar contacts, sensor-fusion summaries, route alternatives/current waypoints, phase, metrics and whitelisted decision evidence. Contact details are limited to the nearest 12 supplied sonar contacts, and path arrays are bounded. Counts report omitted contacts. Moving simulation time backwards clears the previous episode; the summary records resets and frames discarded by the rolling limit.

`sample(snapshot)`, `summary()`, `exportJSONL()` and `clear()` operate entirely in browser memory. JSONL export produces one JSON object per line with schema `reef-rescue-telemetry/v1`; it does not upload data, contain raw camera images, or store credentials. The displayed live stream and download are observations from this simulator, not hardware telemetry. Force values come from the reduced model, sonar contacts from synthetic scene geometry, and species/genet/health eligibility from the known registry. A fusion confidence value is a simulator heuristic, not a calibrated Gemini visual confidence. Actual Gemini decisions are separately marked `source:"gemini"` with their input evidence; scripted decisions must retain their own source label.

## What the demonstration establishes

Browser results describe this browser model and the tested scenarios. The reduced three-degree-of-freedom translational dynamics and yaw presentation do **not** demonstrate Isaac PhysX parity, full six-degree-of-freedom fluid dynamics, realistic cutter forces or fracture mechanics, adhesive chemistry, contact-force validation, biological fusion, survival, or recovery. The browser simulation is not an ultra-realistic physical model. Coral imagery uses specimen scans with artistic living-tissue materials; it is not a reconstructed surveyed reef. The lab is intended for interactive case presentation and controller/recovery exploration. High-fidelity physical validation must still be performed in the authoritative Isaac environment and, ultimately, against measured hardware/field data. Finite scenario tests do not cover every possible setback.

Sonar is simulated geometric range sensing, not a calibrated acoustic propagation model. It cannot establish species, health or genotype. Camera and sonar inputs expose sensor-limited observations to the supervisory model; they do not establish real-world sensor accuracy. A live Gemini Argon planning call was verified against actual seed-42 browser telemetry: it returned a bounded proceed decision and clearance route in 16.7 seconds. This request used synthetic sensor/registry evidence without camera input or Gemma perception; it does not validate the full pipeline. See [recorded evidence](ARGON_LIVE_CHECK.json). Multimodal payload checks still use a JPEG fixture with mocked provider transport; no live Gemma camera call or cuOpt solve has been verified.

Run the policy/server checks without billed API calls:

```sh
python3 -m unittest discover -s tests -p test_lab_server.py -v
node --test tests/lab-simulation.test.mjs
node --test tests/lab-worker.test.mjs
node --test tests/lab-telemetry.test.mjs
```
