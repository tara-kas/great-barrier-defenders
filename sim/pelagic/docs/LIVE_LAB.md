# Reef Rescue AUV live reef lab

Run the editable browser demonstration from the repository root:

```sh
python3 sim/pelagic/scripts/run_lab.py
```

Open **http://127.0.0.1:8090/lab/**. Python 3.10+ and a browser with WebGL2 are required. Three.js and reef assets are bundled; rendering needs no npm installation or Isaac runtime. Production missions require the configured model/solver services. The existing Isaac console and recorded demonstrations are unchanged.

The browser lab owns a separate deterministic simulation. Its selectable cameras, scene editor, water controls, failure injection, event trail and outcome metrics expose an engineering demonstration of the restoration lifecycle. Pause before editing colonies and obstacles. Export scenes to retain configurations; reset creates a fresh episode. The browser mission picks up already detached, permitted loose fragments; it does not cut healthy attached colonies. Dropped fragments and failed placement must be handled before a placement can count as successful. The mission retains registered species/genet eligibility and never presents dead coral as a living recipient.

## Robot perception and base-station planning

The deployed mission uses Gemma visual appearance, an inspectable local decision policy and NVIDIA cuOpt corridor evaluation. Gemini Argon advises on held mission issues through bounded rescan/hold/abort recommendations and reviews completed or aborted episodes. It does not replace the local planner or authorize live actuator motion. Local execution retains collision avoidance, grip/clearance limits and stale-response checks. See [the architecture guide](ARCHITECTURE.md) for endpoint configuration, provenance and the optional Modal deployment path. Gemma hosted on Modal is remote perception; an onboard claim requires a local runtime and measurements on the intended device.

The [file guide](../../../docs/CODE_MAP.md) maps components to source files; the [scenario guide](../../../docs/SCENARIOS.md) describes controls and regression cases.

## Live robot optics and inspection lights

The always-visible robot-camera panel renders an independent **tool optic or forward hull optic** from the same simulation state as the main viewport. These are two camera poses on RESTORE-02, not two separately simulated vehicles. The small view is 384 × 288 at up to 5 updates per wall-clock second. Enlarge it for a timestamped 768 × 576 view updated at up to 2 Hz. The small preview stops refreshing behind the enlarged dialog to avoid rendering both previews unnecessarily. Hidden browser tabs do not render the previews.

Camera targets and pixel buffers are reused by resolution, and preview renders reuse the current main-frame shadow maps. This bounds preview work; it does not guarantee a frame rate on every GPU. A model request always renders a **fresh, separate 768 × 576 tool-camera JPEG** with its actual simulation timestamp and requested target. It never substitutes a cached small preview, a spectator screenshot or a text description for camera pixels. Region labels, current arrows, route lines, sonar markers and selection rings are excluded from all robot-camera captures. Opening or enlarging the inspector does not itself send a model request.

The robot carries a brighter local white spotlight for manipulation and recovery, and a visible violet pilot footprint during recipient/donor inspection. Scene-wide exposure and health classifications are unchanged. UV excitation itself is invisible: the visible violet cone and bounded target-only fluorescence are illustrative inspection cues. Marker brightness follows synthetic exposure and known scenario metadata; it is not a spectral measurement or a way to infer genotype. Inspection uses a visible paired acquisition sequence: the violet pilot and simulated marker run while synthetic exposure accumulates; once the engine declares the capture request ready, that same scene switches to neutral white RGB illumination aimed at the actual inspection target. The fluorescence material is restored before RGB acquisition. The PIP, enlarged inspector, spectator view and Gemma frame all share this lamp state; there is no hidden per-model relighting or health recolouring. White inspection intensity is bounded with range compensation to reduce close-surface clipping. PIP and inspector captions identify UV exposure versus white RGB inspection. Lamp power and attenuation remain uncalibrated rendering parameters, and close-up visual review is still required before a recorded demonstration.

The perception request may include `observation.imageFocus`: known tracked target/gripper positions projected into the actual capture image, normalized from top-left [0,0] to bottom-right [1,1]. This focuses Gemma on the intended visible pixels rather than a larger background colony. It is **not a detected box, validated object localization or proof the target is visible**. The prompt receives no expected kind, health, genet or target-ID hints. Returned `inputImageFocus` preserves this provenance; the JPEG bytes and hash remain unchanged. Offscreen points are omitted, ambiguous pixels remain unknown, and all confidence, gripper and eligibility gates remain active.

## Connecting the complete model loop

**Model-guided autonomy** connects automatically on page load and defaults to Gemma → local policy + cuOpt → local safety checks. Argon is available for escalation when the mission holds on uncertainty or a recovery issue; its advice cannot bypass the camera, registry or safety gates. The UI distinguishes an unconfigured adapter, a configured service that has not started, a warming service, a ready service and an actual received response. Connecting requests service warmup, polls readiness and enables the telemetry uplink. Live control runs at 1× simulation speed. Initial startup never runs the mission automatically: Start remains unavailable until the required services are ready. A later reconnection resumes only if the mission was running before that request. Production exposes no presentation-only start, scripted mission controller or local bypass. Unavailable services keep the mission held.

Production plans require a successful, request-matched cuOpt solve and fresh Gemma evidence. Missing services hold the mission; no partial-stack bypass is exposed. Service readiness is distinct from accepted perception and measured robot-hardware deployment.

Each Gemma frame is associated with the engine's current capture request and target. Late replies for superseded targets or planning gates are discarded. Engine-driven reacquisition and the rescan control request fresh views when visual evidence expires. HTTP waits do not freeze the local physics or reflex controller. Errors remain visible and permit fresh rescan/retry, hold or abort; no local controller substitutes for missing model evidence. Manual Pilot and operator fault injection remain available as explicitly labelled human actions, not autonomous-success evidence.

The active perception contract is **`appearance/v1`**: visible target, object kind, surface appearance, uncalibrated confidence, fragment visibility and gripper state. Biological `health` stays `unknown` and `viabilityKnown` stays false. A clearly visible pigmented coral can pass an appearance gate while its viability remains unestablished by the image. Independent scenario registry eligibility, species and genet must still agree. Initial pickup also requires a fresh view of the actual loose fragment with empty gripper. An attached branch cannot satisfy the loose-stock gate. Unknown appearance, wrong object, stale evidence, mismatched target or a score below 0.70 cannot authorize pickup; retries are bounded.

**Issue assistance:** uncertainty or a recovery issue can be escalated while the robot is held. Argon receives the explicit issue, current structured observations and available Gemma evidence, then may recommend only rescan, hold or abort. A rescan still requires fresh accepted camera evidence before any handling. The episode permits at most three provider attempts, including failures; duplicate issue requests are rejected. The server retains at most 64 episode budgets in volatile process memory. Reconnection keeps the same episode ID; a true reset starts a new one. Restart/redeployment clears server budgets, so these are demo limits rather than durable account quotas. Assistance failures leave the mission held. See the exact `/assist` contract in [the architecture guide](ARCHITECTURE.md).

The **Review completed mission** action sends a bounded completed/aborted episode to Argon between runs. Its summary and recommendations are advisory text, not commands or code changes. Missing review credentials do not block the Gemma/cuOpt mission stack.

**Verification boundary (8 November 2026):** the new visual contract and compact decoder have produced complete real Gemma responses in approximately 2.7–3.2 seconds on actual Isaac camera images. One broad scout view gave an ambiguous fragment classification with unknown gripper; it must not count as correct pickup recognition. The actual Python local policy plus browser engine completed four placements and drop recovery in a cross-language test with explicitly mocked model/solver transports, and asserted that ordinary `/plan` made no Argon calls. That fixture did not verify live issue assistance. A complete successful live-model loose-fragment episode remains a separate acceptance check.

## Persistent observation memory and activity evidence

Accepted Gemma visual observations are saved in browser-local semantic memory, bounded to 128 records with a seven-day expiry. Memory is bound to the exact scene fingerprint, including seed, colonies and obstacles. The architecture panel supports inspection, clearing, export and same-scene import. Records retain model/provider/request provenance and are explicitly historical; no image bytes or credentials are stored. Restored records never satisfy live perception, freshness or registry gates. Up to four relevant historical records may accompany mission context, marked `usableForControl: false`; they never authorize local-policy actions. Argon can receive bounded issue context during a hold or finished-episode context through the explicit review action; historical records remain ineligible for control in either case.

The activity log records actual request starts and awaiting-response states: target/capture identity, camera time, model stage and allowed action/route context. Successful responses add the model name, client-observed latency, concise returned summary or decision reason, and cuOpt route/objective when present. Service warmup transitions, telemetry connection acknowledgements and failures are recorded separately. This is a bounded operational trace, not hidden chain-of-thought. It contains neither raw image bytes nor API keys. Episode export includes the retained transport activity alongside the engine's own event trace.

## Integrated Mission Control evidence

The **Mission evidence** workspace embeds Aryan Patel's dashboard capabilities in the reef lab: semantic map pins, health filters/counts, colony inspection, selectable decision history, evidence/outcome details, source refresh and camera/detection display. Browser map selection highlights the same colony in the 3D scene. Historical decision selection remains stable as new events arrive; following the latest decision is explicit. Pausing the evidence view does not pause vehicle control or the simulation. The original standalone `dashboard/` remains available.

Choose the evidence source deliberately:

- **Lab** shows the current browser registry and actual retained events/decisions. Registry health is known scenario data; no confidence score or camera detection box is invented. A mechanically verified placement is `TREATED`, never biological `RECOVERED`.
- **Recorded team mission** loads bundled actual `mission.runner` / team FSM outputs: **24 colonies, 10 decisions, one treated recipient and one dislodgement**. This is a previously recorded reduced-physics run with synthetic pre-mapped perception, not the current browser mission or live Gemma. No camera frame was saved; the panel must not substitute an illustrative camera image. The underlying asset is `web/lab/assets/team-mission-recorded.json`.
- **Team mission** displays actual relayed Isaac RTX snapshots when available, or reads a configured run directory through the read-only backend bridge. It never commands the browser robot, replaces its world or starts the team FSM. Missing configuration shows an explicit unavailable source; no recorded demo is silently substituted.

To observe current team output, point the local lab server at the directory written by `mission.runner.LiveOutputs`:

```sh
TEAM_RUN_DIR=/absolute/path/to/team-run python3 scripts/run_lab.py
```

The directory must contain `registry.json` and `decisions.jsonl` in the frozen team contracts. An optional `frame.png`, `frame.jpg` or `frame.jpeg` supplies the camera view. Optional `source.json` declares the frame origin explicitly, for example `{"frameSynthetic":true}` for a simulated image; absent metadata leaves the origin unknown. Use atomic replacement when updating files. The canonical dashboard readers parse the data; no client-selected filesystem paths are accepted.

`GET /api/lab/team-state` returns bounded registry, optional detections, decisions, source modification times and a same-origin frame URL. `GET /api/lab/team-frame` serves the optional PNG/JPEG. The panel polls approximately every two seconds while visible and unpaused. Files older than 30 seconds are labelled stale. Missing, malformed or changing data retains the last good view with a visible error; a missing frame does not discard valid registry/decision data. Text/frame files are limited to 2 MiB each, state output to 1 MiB; registry, detection and decision counts report truncation. The bridge is read-only and rejects symlinks/source traversal. A static deployment can show the bundled recording; a live team source requires the configured backend.

## Live Isaac relay and independent browser world

`scripts/push_isaac_feed.py --source http://127.0.0.1:<tunnel-port> --gateway https://<gateway>` reads actual Isaac state and PNG frames through an operator-established loopback SSH tunnel and posts them to the authenticated gateway. Supply `LAB_GATEWAY_TOKEN` through the environment or hidden prompt. The Site reads the latest accepted snapshot through the same team-state/team-frame endpoints; it cannot upload arbitrary source paths or command the Isaac robot.

The view reports actual simulation/camera times, frame hash, source age and camera lag; snapshots older than five seconds or lagging by more than five seconds are stale. It labels imagery as simulated Isaac RTX and registry observations as analytical scene data. Detection boxes are not fabricated, and analytical controller events are not labelled Gemma decisions. This live feed and the editable browser reef have independent state and physics. Watching a real Isaac render does not establish that the browser's Gemma/local-policy/cuOpt mission controlled Isaac or completed the same episode. Pausing the evidence panel affects only that view.

## Legacy Gemini API compatibility (outside the active mission)

The local server retains `/api/lab/decision` for earlier integrations; it is not the active browser mission controller or hosted Modal mission path. To call this separate legacy API, provide `GEMINI_API_KEY` or `GOOGLE_API_KEY` in the **server's environment**, then restart the server. Optional `GEMINI_MODEL` selects a different compatible Gemini model; the default is `gemini-3.5-flash-lite`. The browser never receives the key. A deliberate call to this legacy endpoint enables remote decisions: **the rendered robot tool-camera image and structured sonar/mission telemetry are sent to Google**. The camera image is captured separately from the spectator view. This is a multimodal supervisory controller; it is not a continuous low-level VLM motion policy.

At inspection and recovery gates, the browser supplies a decision ID, observation, camera frame and permissible high-level choices. Gemini receives the frame as an actual image input, not as a description substituted for pixels. It can inspect visible gripper alignment, fragments and contact, and compare those observations with simulated sonar ranges. Gemini returns `proceed`, `retry` or `abort` plus a reason. Registered species/genet/health records remain authoritative; image colour cannot establish health or genetic compatibility. The deterministic engine still owns eligibility, motion, fragment conservation and outcome checks. Model responses cannot inject coordinates or arbitrary commands. The browser must match the pending decision ID before applying the reply.

Requests use Google's [Interactions API](https://ai.google.dev/gemini-api/docs/interactions-overview), [inline image input](https://ai.google.dev/gemini-api/docs/image-understanding), [structured JSON output](https://ai.google.dev/gemini-api/docs/structured-output) and the documented [Gemini 3.5 Flash-Lite model](https://ai.google.dev/gemini-api/docs/models/gemini-3.5-flash-lite), checked November 8, 2026. Requests specify `store: false`, `stream: false`, minimal thinking and 512 maximum output tokens. `store: false` controls retrievable interaction history, not all provider data policies. There is one request in flight, a 25-second socket timeout, a one-second minimum interval, a 30-request/minute process limit, and no application retry. A socket timeout is not a strict total-operation deadline. The optional Worker uses the same contract with a 25-second fetch abort and per-isolate limits; those limits are not global account quotas.

Missing keys, unavailable models, rate limits, invalid output and network errors are visible errors. They do not substitute a local-controller decision or another model. Retry explicitly when the service is available; do not switch to a synthetic mission bypass. Merely configuring a key does not establish that the key, billing or model access works. Tests use a mock provider transport; live provider access requires a real successful call.

## Legacy HTTP contract

`GET /api/lab/health` returns `{ok, geminiConfigured, model, controller, input:"robot_camera_and_sonar_telemetry"}`. Configured only means a nonempty server-side key is present.

`POST /api/lab/decision` accepts JSON:

```json
{"id":"decision-1","observation":{"phase":"inspect","eligible":true,"sonar":{"valid":true,"ranges":[0.5,1.2]}},"allowedActions":["proceed","abort"],"image":{"mimeType":"image/jpeg","data":"BASE64_JPEG_BYTES","camera":"tool","time":12.5}}
```

`image` is optional for API compatibility. A call without it is explicitly reported as `inputMode:"structured_telemetry"` and cannot count as a camera-reviewed decision. JPEG data must be canonical raw base64, not a data URL; the image must be from `camera:"tool"`, with a finite nonnegative simulation timestamp. The limits are 512 KiB decoded image bytes, 768 pixels on each side, 32 KiB structured telemetry independently, and 800 KiB total HTTP body. The standard-library parser validates JPEG framing and SOF dimensions without decoding pixel entropy; the provider must still accept the encoded image. This avoids an extra imaging dependency.

A successful response contains `{id, decision, reason, routeMode, source:"gemini", model, latencyMs, interactionId, usage}` plus `inputMode`, `inputImageSha256`, `inputCamera`, `inputImageTime`, `inputImageWidth` and `inputImageHeight`. `routeMode` is `direct`, `clearance` or null. A non-null route must be explicitly declared in the request's `observation.route.alternatives` (or `observation.navigation.alternatives`) using `id` or `mode`. Missing route suggestions are returned as null for older clients. The model compares the supplied candidate routes with fused sonar hazards and camera evidence; a route suggestion cannot bypass an inspection/recovery decision gate. Invalid or undeclared routes reject the entire reply. Reasons are requested to cite the actual inputs; this validation does not establish that the model's reasoning is correct or calibrated.

The image evidence records exactly which input bytes were sent; image fields are null for telemetry-only calls. The hash proves input identity, not correct visual reasoning. Invalid requests return 400, cross-origin requests 403, unsupported content types 415, rate/concurrency limits 429, provider failures 502, and missing credentials 503. Errors contain `{ok:false,error}`. Responses never include API keys, image bytes or provider error bodies.

The default host is loopback. This development server is not a multi-user deployment backend. If deployed beyond the local machine, use an authenticated application gateway with per-user quotas and a server-side secret store. Static assets alone cannot run the production model-guided mission; it requires this API or an equivalent protected backend. The local server only serves `web/` and `assets/`; repository internals and directory listings are excluded.

## Manual, randomized and mixed environments

Manual pilot commands, seeded scene randomization, mixed coral/rock topology, variable current vectors and moving schools can be inspected through the same browser simulation state. Manual motion and autonomous mission control are distinct pilot modes; recorded pilot mode and input-watchdog status identify who supplied motion commands. Randomized scenes remain subject to eligibility and collision/clearance checks. A chosen seed only makes the seeded scene reproducible; it does not reproduce unrecorded human input or model responses.

The browser's `TelemetryRecorder` samples supplied snapshots at up to **5 Hz of simulation time**, retaining at most **3,000 frames** (approximately ten minutes at that rate). It does not interpolate missing samples or invent measurements. The stream records pose/velocity, pilot state, current vector, applied force components, closest sonar contacts, sensor-fusion summaries, route alternatives/current waypoints, phase, metrics and whitelisted decision evidence. Contact details are limited to the nearest 12 supplied sonar contacts, and path arrays are bounded. Counts report omitted contacts. Moving simulation time backwards clears the previous episode; the summary records resets and frames discarded by the rolling limit.

`sample(snapshot)`, `summary()`, `exportJSONL()` and `clear()` operate entirely in browser memory. JSONL export produces one JSON object per line with schema `reef-rescue-telemetry/v1`; it does not upload data, contain raw camera images, or store credentials. The displayed live stream and download are observations from this simulator, not hardware telemetry. Force values come from the reduced model, sonar contacts from synthetic scene geometry, and species/genet/health eligibility from the known registry. A fusion confidence value is a simulator heuristic, not a calibrated Gemini visual confidence. Current mission proposals retain `source:"local_planner"`, with Gemma and cuOpt evidence recorded separately. Legacy Gemini API responses retain `source:"gemini"`; none may be relabelled as another provider.

## Continuous telemetry uplink

The local recorder remains independent of networking. **Connect telemetry to base** sends its actual sensor frames to the base gateway; selecting a configured Robot + base stack connects this uplink automatically. Frames are sent in non-overlapping batches no more often than every 1.1 wall-clock seconds, with at most five frames and a client-side 60 KiB payload bound per batch. The server's limit is 64 KiB. Larger batches retain fewer frames for the next attempt; a bounded queue reports samples skipped under fast playback or network backpressure.

The UI counts frames only after a matching server acknowledgement and shows the queue, skipped count and latest acknowledged simulation time. Disconnecting or a network failure leaves local physics and recording running. Reconnection is explicit after an error, and a reset to earlier simulation time starts a new stream identity. The uplink carries bounded telemetry, not camera image bytes, and receiving telemetry does not itself prove that a model has interpreted it.

## Simulation model and checks

The browser runs reduced translational dynamics, yaw presentation, current/grip loads, geometric sonar and mechanical contact checks. Registry facts supply biological eligibility and lineage. The camera renders specimen geometry and surface appearance for Gemma; the independent Isaac feed has its own state and controller. Mechanical attachment is the mission completion metric.

From `sim/pelagic`, run the policy/server checks with declared provider doubles:


```sh
python3 -m unittest discover -s tests -p test_lab_server.py -v
node --test tests/lab-*.test.mjs
python3 -m unittest discover -s tests -p test_cuopt_route_adapter.py -v
python3 -m unittest discover -s tests -p test_team_feed.py -v
```

Telemetry rate-limit responses retain at most five unacknowledged frames and retry after at least 1.2 seconds (up to five retries). Older unsent samples are counted as skipped; no receipt is claimed until the gateway acknowledges a matching batch. Persistent rejection or ambiguous network failure disconnects visibly rather than resending potentially acknowledged frames.

## Field-site movement and vehicle model

Click the reef canvas to focus spectator controls: **W/A/S/D** move in the horizontal view direction, **Q** rises and **E** descends. Drag still orbits and scrolling zooms. Escape releases camera focus. Input fields and dialogs do not trigger movement. In **Pilot** mode the same WASD/QE keys command the robot, with left/right arrows for yaw; camera roam is disabled. Local collision limits and the input watchdog remain active.

The visual ROV now includes a capsule pressure hull, flotation pods, protective skids/frame, four ducted propeller assemblies, camera/sonar/light housings and branding. Its measured visual bounds are1.059×0.631×1.120m within the existing1.12×0.65×1.15m design envelope. The articulated arm and jaws retain the same simulation anchors. This is a procedural engineering visualization, not manufacturing CAD, a validated thruster layout or a new dynamics model.

Detached coral uses a cropped real Pocillopora scan with preserved UVs and the source colony’s tissue material; the14cm specimen has a grasp stem anchored to the same physical fragment state. The tool camera fits the fragment and complete jaws together. Fragment acquisition waits for the vehicle to settle before accumulating exposure.
