# Task: Cloud debrief (Argon)

Branch: `cloud-debrief`. Touches only `cloud/`. Don't edit files outside it.

## What exists already (on `main`, don't recreate)

- `agent/decision_log.py` — `DecisionLog.load(path)` reads the JSONL decision
  log you'll feed to Argon. Build against this format even before the
  `agent-fsm` branch lands; fabricate a sample log by hand matching
  `DecisionLogEntry`'s fields if you need one to test against.

## Build

### `cloud/debrief.py`

One real, logged `gemini-4-argon` call (via the Interactions API — this is
the between-dives loop, not the dive loop, so a network call is fine here,
unlike everywhere else in the stack). Input: a decision log (list of
`DecisionLogEntry`, every FSM transition + the evidence behind it). Output: a
structured debrief — what happened, which transitions look wrong, one
concrete suggested patch (e.g. "raise `w3` so pairing favors healthier
donors"). CLI: `python cloud/debrief.py --log <path-to-decision-log>`.

Keep it to debrief only — patch generation and Antigravity-sandboxed
verification are future work, not today's scope (`CLAUDE.md` section 4, Loop
B).

## Definition of done

- `python cloud/debrief.py --log <path>` against a real or fabricated decision
  log makes one real Argon call and prints/saves a structured debrief.
