# PDF / video handoff — 8 November 2026

The separate artifact chat owns final PDF/video delivery. **Current production is model-guided only:** no Start presentation demo, scripted/local mission bypass or partial-stack shortcut. Errors hold, rescan or abort. Manual Pilot and operator fault injection remain explicitly human actions. The pre-removal checkpoint was **120 Node, 38 backend and 11 live/feed/finalizer checks** separately; code changes require fresh verification before declaring the new release validated.

## Verified live episode

`output/video/final/full-episode.json` was independently inspected; [live_stack_completed_placement.json](evidence/live_stack_completed_placement.json) is the concise record. Actual Gemma responses took **2.687–3.201 s**, Argon advised **RESCAN in 22.700 s**, and the cuOpt/local-policy response took **689 ms**. A sensor dropout caused a hold at **T+36.38**, resuming at **T+44.40**. Loose fragment **`donor-1-fragment-1`** was collected at **T+65.083** and mechanically verified at **T+80.55**. Final metrics: **1 placement, 0 drops, 0 recoveries, 0 damage and 0 collisions**.

This establishes one actual-model placement with uncertainty rescan and sensor adaptation. It does not establish live current-induced fragment-drop recovery. Preserve earlier [fragment holds](evidence/live_fragment_visibility_hold.json) and safe-abort runs as distinct diagnostics.

## Final artifacts

- Update `output/pdf/reef-rescue-technical-summary.pdf` using the measured placement evidence and current architecture; generator: `scripts/create_technical_summary.py`. Keep current-drop recovery explicitly unverified until a newer inspected trace establishes it.
- Video: exactly 60 continuous wall-clock seconds of the actual model-guided runtime, with camera, model/solver provenance and actual outcome. Use a disclosed interval of a longer mission if necessary; the verified full episode lasted 80.55 simulated seconds. Do not claim a full one-minute mission by hiding preparation or retiming footage.
- Preserve raw video, capture metadata, episode and telemetry together. Finalize only with continuity/duration checks and excess-tail trimming; `scripts/finalize_live_capture.py` does not verify task success. See [ONE_MINUTE_DEMO.md](ONE_MINUTE_DEMO.md).
- Historical local presentation takes, if already recorded, retain their original scripted controller, synthetic observations and 2× simulation labels/metadata. Removing that shortcut does not rewrite those artifacts or turn them into current model-guided evidence. Never borrow receipts/outcomes between recordings.
- Live application: [Reef Rescue AUV lab](https://reef-rescue-auv-lab.harrish-ayyanar.chatgpt.site/lab/) (owner-private).

## Architecture and claim boundaries

Gemma supplies appearance/fragment/gripper evidence; independent registry facts supply eligibility and lineage. Confidence is uncalibrated. `/plan` uses inspectable policy and native cuOpt subject to engine checks. Argon `/assist` advises only rescan/hold/abort on held issues, with three attempts per episode; `/review` supplies terminal advisory text. Neither bypasses fresh evidence or commands actuators. Image-focus coordinates are tracked projections, not Gemma detections. Gemma/cuOpt currently run remotely on Modal, not validated onboard compute.

The read-only Isaac RTX feed remains independent, with analytical control and simulated observations. Browser modes use reduced physics, collect existing loose stock rather than cutting healthy wild colonies, and establish mechanical placement only. No biological recovery, calibrated hardware dynamics or field reliability is demonstrated. Keep all credentials out of artifacts; do not promise rubric scores.
