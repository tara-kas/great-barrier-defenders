# Reef Rescue — continuous model-guided one-minute take

Production uses the model-guided mission only. **Start presentation demo and local/scripted or partial-stack bypasses are not current production options.** Missing, uncertain or invalid evidence holds the robot for fresh rescan or abort. Manual Pilot and operator fault injection remain available, but manual motion must not be presented as autonomous completion.

## Capture procedure

1. Wait for actual Gemma and cuOpt readiness; start a loose-fragment mission at the production 1× rate. Keep actual camera, provider receipts, source labels and mission time visible.
2. Record one continuous **60-wall-second** interval with the dashboard recorder. The verified complete episode took 80.55 simulated seconds: if recording begins later, disclose the nonzero mission clock. Do not imply the entire mission began at video time zero or speed it up to fit.
3. Introduce an operator fault deliberately and identify it as such. To claim current-induced grip loss, the current must actually increase load and drop the carried fragment; a direct drop button is not equivalent. Fresh accepted camera evidence and local checks must precede recovery of that same ID.
4. Let actual responses determine the outcome. Argon `/assist` may advise only rescan, hold or abort; it cannot authorize handling. Preserve failed or held takes rather than substituting synthetic observations or copied receipts.
5. Download raw video and capture evidence separately; export episode and telemetry. Confirm any claimed recovery/verification occurs before the last retained frame.
6. The artifact chat owns final PDF/video delivery. `scripts/finalize_live_capture.py RAW.webm --evidence RAW.evidence.json --output outputs/live-demo-60s.mp4` validates continuity and trims only excess final tail. It cannot establish task success, pad short footage, hide internal cuts or justify retiming.

## Suggested composition

These are rehearsal windows, not promised runtime or rubric scores.

| Wall time | Evidence to show |
|---|---|
| 00–08 | Reef need and already loose stock; reduced simulation label |
| 08–23 | Actual tool camera, Gemma appearance/visibility and independent registry eligibility |
| 23–43 | Operator disturbance, actual hold/loss, fresh evidence and the controller's response |
| 43–54 | Same-fragment handling and mechanical verification, only if actually reached |
| 54–60 | Real provider/solver trace, final metrics and explicit limitations |

Narration must follow the observed run. A pause, rescan or abort is evidence of conservative behavior, not a completed restoration. A sixty-second lifecycle including model-driven current-drop recovery remains a separate live acceptance target.

## Verified evidence and limits

The independently inspected `output/video/final/full-episode.json` and [completion trace](evidence/live_stack_completed_placement.json) establish actual Gemma responses in **2.687–3.201 s**, Argon **RESCAN in 22.700 s**, sensor-dropout hold **T+36.38–44.40**, and a cuOpt/local-policy response in **689 ms**. Fragment `donor-1-fragment-1` was collected at **T+65.083** and mechanically verified at **T+80.55**: **1 placement, 0 drops, 0 recoveries, 0 damage, 0 collisions**. Live current-induced fragment-drop recovery remains unverified by that trace.

Gemma reports appearance and gripper evidence, not biological viability/genotype. Tracked image-focus points are projections, not detector localizations. Argon provides bounded held-issue assistance and terminal review; `/plan` remains inspectable policy plus cuOpt. Current Gemma/cuOpt services are remote Modal deployments. Mechanical verification is not ecological recovery, and browser physics are reduced. The independent read-only Isaac RTX stream uses its own analytical controller; it is not browser Gemma control.

Historical local presentation recordings, if any, must retain their original scripted/synthetic/2× provenance. They are not current production captures and must never be relabelled as live inference, model-guided autonomy or live recovery evidence.
