# agent

The on-device mission loop. A classical 6-state FSM (`fsm.py`) does the following:
- drives any `RobotInterface`, whether the mock or the Isaac Sim adapter;
- reads and writes the `SemanticSeabedRegistry`;
- logs every transition with the evidence behind it.

It makes no network calls and no model calls. Gemma classification lives in `perception/`, and Argon runs between dives in `cloud/`.

> This replaces the earlier "Gemma picks a tool at ~1 Hz" design. The agreed spec is the FSM in `docs/tasks/agent-fsm.md`.

```
SURVEY_SEABED -> COMPUTE_RESTORATION_PLAN -> NAVIGATE_TO_DONOR ->
HARVEST_FRAGMENT -> NAVIGATE_TO_RECIPIENT -> TRANSPLANT_FRAGMENT -> (back to PLAN)
terminal: MISSION_COMPLETE | ABORTED
```

## Modules

| File | What | Pure? |
|---|---|---|
| `pairing.py` | `J(i,j) = w1·|x_rov−x_i| + w2·|x_i−x_j| − w3·H_i`: same-genet base station rack per open `BLEACHED` colony, sorted by J; carry-aware replan; species-only baseline | pure |
| `base_station.py` | `BaseStation`, `Rack`: stock per genet, take and put back | pure |
| `graft_point.py` | PCA contact point: k-NN normals, up filter (cos 30°), upper 50th percentile, reach plus approach-cylinder clearance, centroid of largest patch | pure |
| `geometry.py` | depth → world points, pose matrices, bbox crop, approach quaternion | yes |
| `config.py` | `FSMConfig` / `PairingWeights` / `GraftConfig` / `NavConfig`, with `to_dict`/`from_dict` | yes |
| `memory.py` | `EpisodicMemory`: rejected donors and recipients with reasons, attempts, harvest counts | stateful |
| `evidence.py` | JSON-safe evidence helpers (`to_jsonable`, `pose_summary`, `entry_summary`) | yes |
| `fsm.py` | `MissionFSM` | the only stateful driver |

## Run

```
python -m pytest agent/tests eval/test_fsm_loop.py      # unit + end-to-end regression
python eval/test_fsm_loop.py --out agent/samples         # regenerate the sample outputs
```

`eval/test_fsm_loop.py` is the regression gate. Any patch to `agent/`, including an Argon-proposed config change, must pass it.

## Plugging in (other branches)

```python
fsm = MissionFSM(robot, registry,
                 config=FSMConfig(),           # or FSMConfig.from_dict(patched_dict)
                 wait=adapter_step,            # advances time dt between control ticks (default time.sleep)
                 perceiver=detect,             # (RGBDFrame, Pose) -> [SemanticMapEntry]; perception branch
                 fragment_held=gripper_ok,     # () -> bool; dislodge detection while carrying
                 placement_verifier=push_test) # (Pose) -> {"stable": bool, ...}
summary = fsm.run(on_step=director)            # on_step runs between states: perturbations, dashboard refresh
```

- **sim:** implement `RobotInterface`. `wait` is how the FSM gives the sim time between `set_cmd_vel` ticks. Use sim time, not wall-clock.
- **perception:** a perceiver returns entries for what the hull camera sees. With no perceiver, survey uses whatever is already in the registry.
- **dashboard:** read `DecisionLog` JSONL and `registry.dump()`. Samples are in `agent/samples/`.
- **cloud debrief:** the `mission_start` entry carries the full config, so a proposed patch is a diff on `FSMConfig.to_dict()`.

## Decision log convention

Every entry is `record(state=<state it was decided in>, action, evidence, outcome)`.

Every `evidence` contains:
- `next_state`
- `rov_pose`
- `sim_time_s`
- `carrying` (genet id or null)

Consecutive entries chain: `entries[i].evidence.next_state == entries[i+1].state`.

`outcome` is `"ok"`, or the reason when something was rejected or failed.

| action | state | key evidence |
|---|---|---|
| `mission_start` | SURVEY_SEABED | `config`, `registry`, which hooks are injected |
| `survey_registry_only` / `survey_waypoint` / `survey_waypoint_skipped` / `survey_complete` | SURVEY_SEABED | waypoint, `hull_frame` depth stats, `detections`, `new`/`updated` ids, `counts_by_status` |
| `select_pair` | COMPUTE_RESTORATION_PLAN | `chosen` J terms (`travel`, `transfer`, `health`, `J`), `genet_id`, `rack`, `recipient`, `skipped`, `ignored_dead`, `stock` |
| `select_recipient_for_carried` / `return_fragment_to_station` | COMPUTE_RESTORATION_PLAN | carried genet, recipient or reason |
| `survey_waypoint_failed` | SURVEY_SEABED | `error`, `consecutive_failures`, `failure_limit`, `perception` |
| `mission_complete` | COMPUTE_RESTORATION_PLAN | `treated`, `skipped_final` (id → reason) |
| `revisit_start` / `revisit_observation` / `revisit_complete` | RETURN_VISIT | `day`, `observation`, `results` |
| `arrive_donor` / `arrive_recipient` / `navigate_failed` | NAVIGATE_* | `navigation`: start, target, final, `residual_m`, `path_ticks`, `max_speed` |
| `fragment_dislodged` | NAVIGATE_TO_RECIPIENT | `navigation.fragment_held=false`, lost fragment, then re-plan |
| `harvest_fragment` / `abstain_harvest` | HARVEST_FRAGMENT | `rack`, `ik_results`, `stock` |
| `transplant_fragment` / `abstain_transplant` / `placement_unstable` / `fragment_returned_to_station` | TRANSPLANT_FRAGMENT | as above plus `placement_verification`, `recipient`, `attempt` |
| `replan_target_changed` | NAVIGATE_* / HARVEST | the registry changed under us (target no longer LIVE or open) |
| `abort` | any | reason; operator needed |

## Behaviours

- **Re-plan every loop:** registry changes mid-mission (new detections, reclassification) change the next pairing.
- **Abstain when unsure:**
  - racks below `min_donor_health` are skipped;
  - a cluster with no valid graft patch is re-observed once, then rejected;
  - recipients over `max_attempts_per_recipient` are dropped;
  - DEAD colonies are never touched; a BLEACHED colony without a confident in-stock genet match is skipped.
- **Dislodged mid-carry** (critical failure, root CLAUDE.md §12): detected through `fragment_held`, logged, then re-plan from the current position to re-acquire.
- **IK unreachable:** at a colony, try the next candidate patch, then reject the site. At the base station, retry, then reject the rack. Then re-plan.
- **Carry-aware:**
  - lower speed while carrying;
  - if a site is rejected while holding a fragment, try the nearest other recipient of that species;
  - otherwise return the fragment to the base station.

## Open items for the team (not resolved here)

1. `RobotInterface` has no time-step or "fragment still attached" method, so both are injected. Proposal: add `is_fragment_attached()`, and agree how the adapter advances time.
2. Assumed conventions:
   - world z-up;
   - `position_world` = bbox centre;
   - `camera_to_robot` uses the OpenCV optical frame (x right, y down, z forward);
   - end-effector approach axis = tool +z (`GraftConfig.tool_axis`).

   Sim and perception owners please confirm.
3. Stock is finite: each fragment taken comes off the rack, and a dislodged one is lost.
4. Placement push test: the hook exists, but with no verifier the log says "unverified" rather than faking a check.
5. `geometry.deproject_depth` overlaps perception's single-pixel `projection.py`. Consolidate after merge.
6. Root §4's richer optimiser (flow, algae risk, uncertainty penalty, value of information) isn't built. `plan_pairs` keeps the same signature if it's extended.
