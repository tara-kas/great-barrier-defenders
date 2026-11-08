# agent

The separate Python research mission loop. A classical FSM (`fsm.py`) drives
`RobotInterface`, consumes the semantic registry and logs transition evidence.
It is not the current browser demo controller. For the active Gemma E4B / Argon /
cuOpt pipeline, start with the [project README](../README.md) and
[system architecture](../docs/ARCHITECTURE.md).

This package makes no network or model calls. The Python integration in
`mission/` supplies perception results and adapter hooks. Its placement and
return-visit statuses represent the supplied observations; they do not establish
field treatment efficacy. Historical build plans in `docs/tasks/` are not the
current system specification.

```
SURVEY_SEABED -> COMPUTE_RESTORATION_PLAN -> NAVIGATE_TO_DONOR ->
HARVEST_FRAGMENT -> NAVIGATE_TO_RECIPIENT -> TRANSPLANT_FRAGMENT -> (back to PLAN)
recovery branch: RECOVER_FRAGMENT -> NAVIGATE_TO_RECIPIENT
optional follow-up: RETURN_VISIT
terminal: MISSION_COMPLETE | ABORTED
```

## Modules

| File | What | Pure? |
|---|---|---|
| `pairing.py` | `J(i,j) = w1·|x_rov−x_i| + w2·|x_i−x_j| − w3·H_i`: same-genet inventory source per open `BLEACHED` colony, sorted by J; carry-aware replan; species-only baseline | pure |
| `base_station.py` | `BaseStation`, `Rack`: station racks or positioned reef sources, persistent fragment IDs, take and put back | stateful |
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

## Adapter integration

The following is an interface sketch with initialized robot, registry, inventory
and adapter callbacks.

```python
fsm = MissionFSM(robot, registry,
                 base_station=inventory,       # required BaseStation
                 config=FSMConfig(),           # or FSMConfig.from_dict(patched_dict)
                 wait=adapter_step,            # advances time dt between control ticks (default time.sleep)
                 perceiver=detect,             # (RGBDFrame, Pose) -> [SemanticMapEntry]
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
| `fragment_dislodged` | NAVIGATE_TO_RECIPIENT | `navigation.fragment_held=false`, lost fragment, then recovery or re-plan |
| `recover_fragment` / `recovery_failed` | RECOVER_FRAGMENT | persistent fragment ID, independent held check, recovery result |
| `harvest_fragment` / `abstain_harvest` | HARVEST_FRAGMENT | `rack`, `ik_results`, `stock` |
| `transplant_fragment` / `abstain_transplant` / `placement_unstable` / `fragment_returned_to_station` | TRANSPLANT_FRAGMENT | as above plus `placement_verification`, `recipient`, `attempt` |
| `replan_target_changed` | NAVIGATE_* / HARVEST | the registry changed under us (source or recipient no longer eligible) |
| `abort` | any | reason; operator needed |

## Behaviours

- **Re-plan every loop:** registry changes mid-mission (new detections, reclassification) change the next pairing.
- **Abstain when unsure:**
  - racks below `min_donor_health` are skipped;
  - a cluster with no valid graft patch is re-observed once, then rejected;
  - recipients over `max_attempts_per_recipient` are dropped;
  - DEAD colonies are never touched; a BLEACHED colony without a confident in-stock genet match is skipped.
- **Dislodged mid-carry:** detected through `fragment_held` and logged. With an adapter recovery hook, require recovery of the same persistent fragment ID plus an independent held check. Without that capability, re-plan for replacement supply; do not report same-fragment recovery.
- **IK unreachable:** at a colony, try the next candidate patch, then reject the site. At the base station, retry, then reject the rack. Then re-plan.
- **Carry-aware:**
  - lower speed while carrying;
  - if a site is rejected while holding a fragment, try the nearest other eligible recipient of the same genet and compatible species;
  - otherwise return to a supported source fixture; if the adapter rejects return, stop and retain the fragment.

## Adapter requirements and limits

`RobotInterface` does not supply time stepping, a fragment-held sensor or a
placement verifier. Supply those callbacks explicitly. `mission.run_mission`
requires held and placement checks by default; its `allow_unverified` override
is for development and does not constitute verified placement evidence.

Optional adapter capabilities include `inspect_donor`, `inspect_recipient`,
`prepare_pair`, `held_fragment_id`, `recover_lost_fragment`, `contact_candidate`,
`navigation_pose`, `get_sim_time`, and `can_return_fragment`. Evidence must come
from the implemented adapter; absent hooks must not be described as sensors.

Geometry assumes world z-up, bounding-box-centre registry positions, an OpenCV
optical camera frame (x right, y down, z forward), quaternion order xyzw and the
configured end-effector approach axis (`GraftConfig.tool_axis`). Validate these
conventions when adding an adapter.

Inventory is finite. A successful same-fragment recovery does not consume a
second source fragment. The pairing cost above is a simple research objective;
it does not include a field-calibrated flow, algae-risk or uncertainty model.
The browser demo's native cuOpt routing is a separate implementation.
