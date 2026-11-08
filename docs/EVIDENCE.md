# Evidence and reproducibility

## Recorded live-model episode

The canonical raw artifact is [live-model-episode.json](evidence/live-model-episode.json). It was exported at **2026-11-08T13:41:14.099Z**. Its SHA-256 is:

```text
18ccaa83ff528e0536ea3e738c10f4fee185c0c014fc036e4c802d4f984ce115
```

The [readable result summary](../sim/pelagic/docs/evidence/live_stack_completed_placement.json) records source build `b5967bb2b6399ab387408812c9344e0e1606c680` and the same raw-artifact hash. That build identifies the recorded deployment, not a claim that later source edits were used in this episode. Preserve raw bytes when copying the artifact.

| Outcome | Recorded value |
| --- | --- |
| Final state | Complete; 80.55 simulated seconds |
| Mechanically verified placements | 1 |
| Collisions / drops / recoveries | 0 / 0 / 0 |
| Fragment | `donor-1-fragment-1` |
| Recipient | `recipient-1` |
| Gemma | `gemma-4-E4B-it`, Modal, five responses |
| Argon | `gemini-4-argon`, one assistance response: RESCAN |
| Route | `reef-local-policy-v1`, native cuOpt `26.10.0` |

The event sequence contains uncertain source perception, Argon-assisted rescan, a camera-dropout hold and return to the same mission, fresh fragment perception, route approval, collection and mechanical verification. No additional live drop-recovery result is implied.

Browser request/response messages record Gemma latencies of **3075, 2877, 3201, 2824 and 2687 ms**. Argon assistance records **22700 ms**. The route response records **198 ms** cuOpt solve time. These scopes differ: browser inference round-trip and native solve duration are not interchangeable. The sample is too small to establish a service-level guarantee.

## Additional evidence

The [saved uncertainty-abort episode](evidence/live-model-uncertainty-abort.json), exported at `2026-11-08T13:40:40.359Z`, preserves a negative live-model outcome from the local workspace. The episode ends after the 90-second assistance hold limit, with zero placements and zero collisions; it does not turn unresolved perception into approval. Its SHA-256 is `ae974eb29a0f0e8955eb6d229af0357bc3da7240c0ad7402ea6ea5e12ba429aa`. It is an independent run, not an event appended to the completed episode.


- [Fragment-visibility hold](../sim/pelagic/docs/evidence/live_fragment_visibility_hold.json) — negative live case.
- [Earlier safe abort](../sim/pelagic/docs/evidence/live_stack_safe_abort.json) — historical architecture using Argon in normal planning; inspect its source before generalizing.
- [UV uncertainty](../sim/pelagic/docs/evidence/gemma_uv_uncertainty.json) — appearance uncertainty evidence.
- [Scenario matrix](SCENARIOS.md) — deterministic regression coverage, including fault handling and same-ID recovery. Provider doubles do not add live model samples.

## Submission materials

- [Current technical summary](submission/technical-summary-current.pdf) — updated after the completed placement.

The pipeline video explains the workflow. The raw episode, source paths and tests provide the repository's auditable implementation evidence.

## Verify locally

```bash
python3 tools/verify_submission.py
```

The verifier checks raw-artifact integrity, consistency with the recorded summary, required model identity and local documentation targets. Run the software regressions in [SETUP](../SETUP.md) to test the current checkout. No static artifact can prove a current endpoint is healthy: a new deployment needs its own actual inference and complete mission run.

## Repository review checks — 8 November 2026

The root Python review used Python 3.10.4 and pytest 9.1.1:

| Command after `python -m pytest -q` | Result |
| --- | --- |
| `agent/tests eval/test_fsm_loop.py eval/test_mission.py eval/test_living_reef_mission.py eval/test_reef_adapter.py` | 141 passed, including 41 new navigation/configuration safety cases |
| `perception/tests cloud dashboard` | 119 passed, 1 skipped |
| `eval/test_moore_reef.py` | 24 passed |
| Previously skipped `perception/tests/test_gemini_client.py::test_actual_sdk_serializes_v1_request_with_offline_transport`, in a temporary environment with `google-genai==2.33.0` | 1 passed |

The navigation checks cover invalid/nonfinite sensor data, invalid configuration, callback/adapter errors, arithmetic overflow and stop commands on exit. These are offline software regressions, not physical actuator tests. The initial interpreter lacked `google.genai`; installing the declared SDK in a temporary environment allowed the one skipped serialization test to pass against an offline HTTP transport. Across these commands, all 285 distinct tests passed. No live model request is made by these commands. HTTP tests ran with local port-binding permission.

The complete simulator unittest suite also passed: **179 tests**, plus **7 pytest tests** covering current dynamics and gripper linkage. Run these from `sim/pelagic` with `python -m unittest discover -s tests` and `python -m pytest -q tests/test_current_dynamics.py tests/test_gripper_linkage.py`. Across the root and simulator Python suites, **471 distinct tests passed**. The final combined checkout also passed all **120 JavaScript lab tests** via `node --test tests/lab-*.test.mjs`, for **591 passing checks** in total.

The submission verifier passed on the saved raw episode and linked documentation. A temporary altered copy confirmed that it rejects changed raw bytes and missing local targets. `git diff --check` also passed. Current browser/gateway test commands are listed in [SETUP](../SETUP.md) and their scenario coverage in [SCENARIOS](SCENARIOS.md).

Remaining acceptance work is listed in [IMPLEMENTATION_STATUS](IMPLEMENTATION_STATUS.md).
