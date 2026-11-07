# Task: Agent / Planning / FSM

Branch: `agent-fsm`. Touches only `agent/`, `eval/synthetic_scene.py`,
`eval/mock_robot.py`, `eval/test_fsm_loop.py`. Don't edit files outside these.

## What exists already (on `main`, don't recreate)

- `agent/robot_interface.py` — `RobotInterface` ABC your FSM drives, plus
  `Pose` / `RGBDFrame`. Implement against this; don't change its shape
  without flagging it to the team.
- `agent/decision_log.py` — `DecisionLog` / `DecisionLogEntry`. Use this for
  every FSM transition; the dashboard and Argon debrief both consume it.
- `perception/registry.py` — `SemanticMapEntry` / `SemanticSeabedRegistry`.

## Build

### `agent/pairing.py`

Donor-recipient cost function:

    J(i, j) = w1*|x_rov - x_i| + w2*|x_i - x_j| - w3*H_i

`w1=1.0, w2=1.5, w3=2.0` defaults. For each unvisited DEAD cluster `j`, pick
the LIVE donor `i` of the same species minimizing `J`. Pure function over
`SemanticSeabedRegistry` entries — trivially unit-testable with known
positions/health scores.

### `agent/graft_point.py`

PCA graft-point selector on a point cloud of the dead coral structure:

1. k-NN (k=15) surface normal estimation per point — `scipy.spatial.cKDTree`
   + NumPy eigendecomposition of the local covariance is enough, skip Open3D
   unless there's time to spare.
2. Upward-facing filter: keep points where `normal · [0,0,1] > 0.866`
   (cos 30°), prioritize the upper 50th-percentile height.
3. Reject points whose approach cylinder (along the normal) intersects
   neighboring coral or lies outside manipulator reach.
4. Target = centroid of the largest contiguous valid patch; gripper
   approaches anti-parallel to that patch's normal.

### `agent/fsm.py`

`MissionFSM`, 6 states, looping back to state 2 until all restorable clusters
are processed:

    SURVEY_SEABED -> COMPUTE_RESTORATION_PLAN -> NAVIGATE_TO_DONOR ->
    HARVEST_FRAGMENT -> NAVIGATE_TO_RECIPIENT -> TRANSPLANT_FRAGMENT -> (loop)

Takes a `RobotInterface` and a `SemanticSeabedRegistry` as constructor
arguments — must run identically against the mock robot (your tests) and
whatever the sim team's real adapter turns out to be. Call
`DecisionLog.record(state, action, evidence, outcome)` on every transition —
evidence must be the actual sensor/classification data that caused the
decision, not a placeholder (`CLAUDE.md` section 8).

## `eval/` (same branch — this is your test harness)

- `synthetic_scene.py`: 15-20 synthetic `SemanticMapEntry` rows, 2-3 species,
  mixed LIVE/DEAD/BLEACHED, random positions in a 10x10m seabed.
- `mock_robot.py`: `MockRobotInterface` implementing the ABC — no physics,
  just position bookkeeping and instant attach/detach.
- `test_fsm_loop.py`: run `MissionFSM` end-to-end against the mock + synthetic
  scene. Assert every DEAD cluster ends `RESTORED` and the decision log has
  evidence for every transition. This is the regression test `CLAUDE.md`
  section 8 requires before any patch (including Argon-proposed ones) merges.

## Definition of done

- `pytest eval/test_fsm_loop.py` passes.
- Unit tests for `pairing.py` (known inputs -> expected match) and
  `graft_point.py` (synthetic point cloud with a known flat patch -> selector
  picks its centroid).
