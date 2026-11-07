# Task: Dashboard

Branch: `dashboard`. Touches only `dashboard/`. Don't edit files outside it.

## What exists already (on `main`, don't recreate)

- `perception/registry.py` — `SemanticSeabedRegistry` you read from.
- `agent/decision_log.py` — `DecisionLog.load(path)` reads the JSONL decision
  log the FSM writes; build against this format even before the `agent-fsm`
  branch lands.

## Build

3-panel "Mission Control" view:

- **3D viewport** — placeholder/simple scatter of ROV + coral positions from
  the registry. The full Isaac Sim feed comes later from `/sim`, not your job
  today.
- **Camera feed** — detection boxes overlaid on a frame. Until the real sim
  feed exists, use the synthetic frames the perception branch generates in
  `eval/fixtures/` (via `eval/generate_synthetic_frames.py`, Nano Banana).
  Label these frames `synthetic` on screen — never presented as real footage
  (`CLAUDE.md` section 6).
- **Top-down map** — pins colored by `health_status`: red (`DEAD`), green
  (`LIVE`), blue (`RESTORED`). Update live as the registry changes.

You don't need the real FSM running to build and test this: point it at a
canned `SemanticSeabedRegistry` dump + a canned decision-log JSONL file for
now (ask the `agent-fsm` branch owner for a sample once their
`test_fsm_loop.py` run produces one, or fabricate one by hand matching the
schema in `perception/registry.py` / `agent/decision_log.py`).

## Definition of done

- Dashboard opens and renders all three panels against synthetic/canned data.
- Map updates when the underlying registry/log data changes.
- Swapping in real data later is a config/data-source change, not a rewrite.
