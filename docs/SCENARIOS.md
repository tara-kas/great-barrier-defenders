# Scenario and verification guide

This guide describes the current **loose-fragment browser mission**. It separates recorded live-model results from deterministic regression tests. Start with the [README](../README.md) for system setup and the [judging guide](JUDGING_GUIDE.md) for claim-to-evidence questions.

## Mission scenario

A reef restoration team has registered a living, bleached recipient and a compatible source of already-detached coral fragments. The robot must inspect the candidate and stock, collect an eligible fragment, transport it without harming the surroundings, place it on the recipient, and verify mechanical attachment. It may decline or abort when the required evidence is unavailable.

The [compact scene](../sim/pelagic/configs/reef_lab_compact_recovery.json) is a configured, seed-42 test environment, not a surveyed reef. It sets one placement as the goal, a nominal current of 0.08 m/s and 8 m visibility. Its eligible `donor-1` and `recipient-1` pair are registered as *Pocillopora damicornis*, lineage `G1`; other unregistered colonies remain habitat. The engine excludes inaccessible stock. [Scene notes](../sim/pelagic/configs/reef_lab_compact_recovery.md) explain its geometry and the limits of offline timing estimates.

Registered identity, biological eligibility and lineage are **scenario inputs**. Gemma sees actual rendered robot-camera pixels and reports appearance, target visibility and fragment/gripper observations. Its output does not establish biological viability or genotype. Synthetic UV markers supply a simulated inspection gate, not a genetic assay.

## Expected sequence

1. Select an eligible registered source/recipient pair; reject dead, unknown-lineage, incompatible or inaccessible stock.
2. Inspect the recipient using the simulated UV exposure gate and a fresh white-light robot-camera capture. In loose-stock mode, the source colony is checked through the registry; the handled fragment receives its own visual inspection.
3. Send captures to Gemma. Require the appropriate visible object and appearance evidence, with the configured confidence and freshness checks.
4. If perception is uncertain or another issue occurs, hold the robot and request bounded Argon advice. Only `rescan`, `hold` and `abort` are accepted. A rescan must obtain new evidence.
5. Inspect the actual loose fragment and gripper. The local policy checks eligibility and evidence; cuOpt evaluates declared route alternatives.
6. Pick up the existing fragment. Loose mode never enters a cutting phase or invents replacement stock.
7. Traverse under local terrain, habitat, wildlife, current and grip checks. Loss of the fragment starts same-identity recovery with a new camera capture.
8. Place and mechanically verify attachment before incrementing the placement count. Continue to another eligible task if the configured goal requires it; otherwise finish.

The implementation is in [simulation.mjs](../sim/pelagic/web/lab/simulation.mjs), [app.mjs](../sim/pelagic/web/lab/app.mjs) and [lab_server.py](../sim/pelagic/reefsim/lab_server.py). The state machine, numerical safety limits and reproducible seeds are intentional engineering controls. Model calls are identified by their request/response receipts.

## Regression scenarios

The tests below exercise the real controller and adapters with declared fixtures or model doubles. They establish repeatable behavior under the tested inputs; they do not count as additional live Gemma/Argon runs. Test titles are quoted exactly so reviewers can locate them.

| Case | Required behavior | Regression evidence |
| --- | --- | --- |
| Every available loose fragment | Preserve the fragment ID, collect reachable stock, leave the healthy colony unchanged, never cut it. | [Simulation tests][simtests]: `every eligible loose stock fragment is grounded, reachable and collected without cutting a healthy colony` covers 8 fragments across 3 seeds (24 fixture pickups). |
| Dead, missing-lineage or incompatible candidates | Exclude the pair; finish without an unsafe intervention or abort when no valid stock remains. | [Simulation tests][simtests]: `loose fragment mode rejects dead or unknown-lineage sources and dead recipients`; `unknown/mismatched lineage and dead colonies never form a pair`. |
| Uncertain appearance or unknown gripper state | Hold or obtain fresh evidence; never infer eligibility from an uncalibrated score alone. | [Simulation tests][simtests]: `visual appearance gates are independent from registry viability and never assert RGB health`; [backend tests][backendtests]: `test_incomplete_or_contradictory_visual_response_is_rejected`. |
| Camera moves during fragment acquisition | Wait for a settled view and reset exposure when motion resumes. | [Simulation tests][simtests]: `fragment camera exposure waits for a settled vehicle and resets on motion`. |
| Stale, replayed, premature or wrong-target packet | Reject the packet or physically rescan before proceeding. | [Simulation tests][simtests]: `perception packet freshness, ordering and replay validation rejects unsafe updates`; `capture target binding rejects wrong-camera and early frames while allowing an explicit fresh retry`. |
| Current-induced grip loss | Let the modeled current affect the held fragment, retain the same ID and require a new recovery view. | [Simulation tests][simtests]: `loose full-stack fixture inspects actual pickup fragment and preserves its identity through current-induced loss`; `a new fragment capture invalidates an otherwise recent pre-drop pickup image`. |
| Fault arrives during Argon assistance | Keep current/grip physics and local safety running while mission progression is held. | [Simulation tests][simtests]: `assistance hold preserves live current and grip-loss physics without advancing the mission`. |
| Argon unavailable, malformed, repeated or over budget | Do not grant handling authority. Limit attempts and hold or abort. | [Backend tests][backendtests]: `test_argon_assist_is_advisory_real_protocol_and_bounded_per_episode`; `test_invalid_argon_assistance_never_authorizes_proceed_and_consumes_attempt`; [simulation tests][simtests]: `assistance hold is bounded, manual override clears it and explicit abort is terminal`. |
| Transient assistance failure versus permanent invalid output | Retry transient failures with fresh telemetry inside the original three-attempt and active hold budgets; never retry forbidden advice into motion. | [Assistance tests](../sim/pelagic/tests/lab-assistance.test.mjs): automatic retry, timeout, cancellation, reset, explicit retryability and selected-fragment binding. |
| Colony rescan and image focus | Use the same physical optic for preview and inference, fit the tracked specimen and bound rescan changes. | [Camera tests](../sim/pelagic/tests/lab-camera.test.mjs): real-mesh coverage, shared pose, unchanged handling contact and fragment projection. |
| Gemma unavailable or invalid | Report the failure explicitly; never replace it with an empty safe scene or a fabricated model result. | [Backend tests][backendtests]: `test_gemma_outage_or_invalid_estimate_never_looks_like_clear_scene`. |
| cuOpt failure or inconsistent route evidence | Reject an absent, unsolved or mismatched configured solver result. | [Simulation tests][simtests]: `configured cuOpt cannot be omitted, mismatched, or replaced with an unsolved heuristic`; [backend tests][backendtests]: `test_failed_or_nonfinite_solver_cannot_reach_argon`. |
| Poor placement | Recheck attachment; an attempted placement is not automatically counted as success. | [Simulation tests][simtests]: `bad placement must be mechanically reverified before success`. |
| Visibility, camera or sustained-current failure | Hold for recovery; abort persistent unsafe conditions. | [Simulation tests][simtests]: `persistent unsafe conditions abort rather than reporting success`; `environment recovery restores the current phase status immediately`. |
| Wildlife, habitat and route constraints | Yield or replan using the shared geometry and local clearance checks. | [Simulation tests][simtests]: `near-seabed crab encounter triggers actual vehicle yielding`; `dense visible habitat has shared broadphase and sonar proxies`; `direct and clearance routes follow distinct waypoints without teleportation`. |
| Stale remembered observations | Retain useful context without authorizing action from it. | [Memory tests](../sim/pelagic/tests/lab-semantic-memory.test.mjs): `memory retention is bounded, deduplicated and expires without refreshing stale evidence`. |
| Complete adapter/controller wiring | Run actual Python adapters and JavaScript mission logic with explicit provider doubles. | [Cross-language test](../sim/pelagic/tests/lab-pipeline-contract.test.mjs): `real backend adapters and engine complete the full loop with mocked model/solver transports`. |

Run the browser/controller and backend checks from the repository root:

```bash
cd sim/pelagic
node --test tests/lab-*.test.mjs
python3 -m unittest tests.test_lab_server tests.test_live_feed tests.test_live_stream_capture
```

The HTTP tests need permission to bind a local ephemeral port. These commands use fixtures; they do not provision Modal or make live paid inference requests.

## Recording a mission

Select **Robot + base**, wait for service readiness and start the mission. Use **Export** to save the episode and activity log. To exercise current-driven recovery, inject **Current surge** while a fragment is carried. Inspect the recorded fragment ID, current/grip readings, camera captures, model receipts, recovery transitions and placement counters together. See [EVIDENCE](EVIDENCE.md) for artifact fields and integrity checks.

[simtests]: ../sim/pelagic/tests/lab-simulation.test.mjs
[backendtests]: ../sim/pelagic/tests/test_lab_server.py
