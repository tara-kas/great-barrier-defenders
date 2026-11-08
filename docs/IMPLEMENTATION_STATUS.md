# Implementation status and next acceptance steps

## Implemented and inspectable

- Current browser mission: registered loose stock, rendered camera acquisition, real Gemma integration, bounded Argon assistance, native cuOpt route solving and local safety/placement verification.
- Freshness, replay and target-binding checks; independent eligibility and lineage registry.
- Sensor/provider failure holds and aborts, same-ID fragment recovery logic, local obstacle/wildlife checks and bounded semantic memory.
- Server-side authentication, explicit readiness/failure responses, episode/activity export and read-only Isaac feed.
- One saved actual-model episode with uncertainty escalation, sensor-dropout recovery and one completed placement. [Evidence](EVIDENCE.md) contains its raw artifact and measurements.

## Remaining acceptance work

| Priority | Concrete next step | Completion evidence |
| --- | --- | --- |
| 1 | Run the current deployed source with actual Gemma/cuOpt/Argon after runtime edits. Trigger a current disturbance while carrying a fragment. | One continuous episode containing fresh post-drop capture, same-ID reacquisition, verified placement, source revision and model receipts. |
| 1 | Repeat nominal and negative cases across varied scene seeds, visibility and currents; include provider timeout and malformed output. | Versioned run set with successes, safe holds/aborts and failures all retained; no selection of successful runs only. |
| 2 | Calibrate appearance/fragment detection against held-out labeled images, then choose thresholds. | Accuracy, false acceptance and confidence-calibration measurements. The existing 0.70 provider-score gate is not a calibrated probability. |
| 2 | Package the selected Gemma model and required services on the target robot computer; test with networking disconnected. | Actual model residency plus measured peak memory, power, latency and a disconnected completed mission within a stated budget. |
| 2 | Make assistance accounting durable if serving multiple workers or requiring cross-restart limits. | Concurrent/restart tests showing episode budgets remain enforced. Current accounting is process-local. |
| 3 | Connect physical sensing/actuation and validate contact/force limits, with a reviewed ecological protocol before field intervention. | Hardware tests and qualified ecological assessment. Browser mechanical success cannot establish biological benefit. |

The Python research mission is separately testable; its adapter path is not automatically the deployed browser path. Keep its test results and deployment claims scoped to the implementation that produced them.

These are bounded work items, not reasons to weaken the gates or replace missing model outputs. The quickest route to stronger evidence is to run the existing instrumented pipeline through the missing acceptance cases and retain every outcome.
