# Operating status and validation

## Implemented and inspectable

- Current browser mission: registered loose stock, rendered camera acquisition, real Gemma integration, bounded Argon assistance, native cuOpt route solving and local safety/placement verification.
- Freshness, replay and target-binding checks; independent eligibility and lineage registry.
- Sensor/provider failure holds and aborts, same-ID fragment recovery logic, local obstacle/wildlife checks and bounded semantic memory.
- Server-side authentication, explicit readiness/failure responses, episode/activity export and read-only Isaac feed.
- Network-isolated Gemma E4B image inference measured on Spark GB10 with pinned weights and resource evidence. [Edge deployment](EDGE_DEPLOYMENT.md) records its scope.
- Automatic bounded assistance retries, selected-fragment binding, shared camera optics and sanitized failure diagnostics.
- One saved actual-model episode with uncertainty escalation, sensor-dropout recovery and one completed placement. [Evidence](EVIDENCE.md) contains its raw artifact and measurements.

## Deployment checks

| Priority | Concrete next step | Completion evidence |
| --- | --- | --- |
| 1 | Complete the current-disturbance recovery case after assistance transport checks. | Latest Spark trial: inspection, native route solve, collection and one current-induced drop; safe abort after Argon timeout. Completion target: same-ID recovery and verified placement in one episode. |
| 1 | Enforce a total Argon transport deadline and release the active-request slot on expiry. | The configured 25-second socket timeout allowed a Spark request to outlast the browser timeout. A bounded wall-clock transport test and successful retry are required. |
| 1 | Repeat nominal and negative cases across varied scene seeds, visibility and currents; include provider timeout and malformed output. | Versioned run set with successes, safe holds/aborts and failures all retained; no selection of successful runs only. |
| 2 | Calibrate appearance/fragment detection against held-out labeled images, then choose thresholds. | Accuracy, false acceptance and confidence-calibration measurements. The existing 0.70 provider-score gate is not a calibrated probability. |
| 2 | Complete a mission using the measured Spark Gemma service and local native cuOpt; test loss of external networking. | Local Gemma residency and image-inference measurements are now recorded; remaining evidence is a disconnected completed mission and a complete system resource/power budget. |
| 2 | Make assistance accounting durable if serving multiple workers or requiring cross-restart limits. | Concurrent/restart tests showing episode budgets remain enforced. Current accounting is process-local. |
| 3 | Connect physical sensing/actuation and validate contact/force limits, with a reviewed ecological protocol before field intervention. | Hardware tests and qualified ecological assessment. Browser mechanical success cannot establish biological benefit. |

The Python research mission is separately testable; its adapter path is not automatically the deployed browser path. Keep its test results and deployment claims scoped to the implementation that produced them.

Retain each deployment’s source revision, provider receipts and complete episode export when running these checks.
