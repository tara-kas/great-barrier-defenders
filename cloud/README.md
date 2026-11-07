# cloud

Between-dives loop (Argon, via the Interactions API): debrief (review run logs/video, label failures), coder (propose patches to planner weights / behaviour tree / controller), verifier (run patches against the `/eval` regression suite, promote only if nothing regresses **and a human approves**), scene generation/critique for Isaac Sim assets.

Owner: TBD (see CLAUDE.md section 10).

Never called from the dive loop (`/control`, `/perception`, `/agent` must stay network-free during a run). Human approval gate required before any promoted patch.

## Debrief

One real `gemini-4-argon` call over a finished mission's decision log. It returns a verdict, a summary, the suspect transitions and one suggested patch. Patches are proposals only: nothing here applies or tests them.

```
python cloud/debrief.py --log <decision-log.jsonl> --html report.html
```

`GEMINI_API_KEY` comes from `.env`. Each run saves its debrief, interaction ID and token counts to `cloud/runs/` (or `--out`). That folder is git-ignored; `example_run/` holds one committed run as proof of a real call.

| Flag | Purpose |
|---|---|
| `--html PATH` | Write a self-contained report. Opens offline. |
| `--expected PATH` | Score the debrief against an answer key. The key is never sent to Argon. |
| `--from-json PATH` | Re-render a saved debrief with no API call. The page says so, and it refuses a log that differs from the original. |
| `--thinking low\|medium\|high` | Reasoning depth. Default `high`. |

**Verification.** Argon must cite log values for every flag. `check_citations` looks each one up in the log, and the report marks any that are not there. This shows the quoted evidence exists, not that Argon's reasoning from it is right.

**Failures.** A failed call, an incomplete interaction or invalid output exits non-zero and writes no debrief, with no fallback output. This code does not retry. The SDK's own default retries 408, 409, 429 and 5xx responses up to 4 times, so one run can mean more than one HTTP request after a transient error. Invalid output is kept as `<out>.raw.txt`.

**Sample logs.** `sample_logs/fabricated_*.jsonl` are hand-written, not real missions, and the report says so.

- `flawed`: three flaws, each with its limit recorded in the evidence.
- `subtle`: three flaws with no limit beside them.
- `clean`: no flaws, to catch invented problems.

**What the FSM needs to log.** The debrief can only judge what the log contains. For pairing, log every candidate considered, not only the winner. Log limits next to measured values, for example `normal_dot_z` with `normal_dot_z_min`.

**Tests.** `pytest cloud/test_debrief.py` runs offline with canned responses. It covers parsing and the report, not Argon's judgement. The sample logs cover that, in live runs.
