# CLAUDE.md — agent-fsm branch (`agent/`)

> **Premise changed (root `CLAUDE.md` section 15).** The robot now treats `BLEACHED` coral with same-genet fragments from a base station, and skips `DEAD`. Where this file still describes LIVE donors and DEAD recipients, the root file wins.

Scoped context for work on the mission FSM, pairing, and graft-point selection.
The root [`CLAUDE.md`](../CLAUDE.md) still applies; where this file and the
root disagree, `docs/plan.md` and `docs/tasks/agent-fsm.md` (the newer spec)
win for *this branch's code*, and the conflict should be flagged to the team.

Sources: `docs/tasks/agent-fsm.md`, `docs/tasks/README.md`, `docs/plan.md`,
root `CLAUDE.md` §4, §8, §11, §12, and the frozen contracts listed below.

## 1. Scope and boundaries

**Branch:** `agent-fsm`. **May touch only:**

- `agent/` (new: `pairing.py`, `graft_point.py`, `fsm.py`, unit tests)
- `eval/synthetic_scene.py`
- `eval/mock_robot.py`
- `eval/test_fsm_loop.py`

**Do not edit:** root `CLAUDE.md`, other branches' task docs, other module
directories, or the frozen contracts (below). New dependency → append to the
bottom of `requirements.txt` and flag it; don't reorder. Rebase onto `main`
before a PR; never merge `main` into the branch.

## 2. Frozen contracts (read, build against, don't reshape)

Changing any of these is a team sync message, not a unilateral edit.

- **`agent/robot_interface.py`** — `RobotInterface` ABC the FSM drives:
  `get_pose()`, `set_cmd_vel(linear, angular)`, `lock_base()` /
  `unlock_base()`, `get_hull_rgbd()` (downward, 0.5–3.0 m survey),
  `get_wrist_rgbd()` (close range, 0.15–0.5 m, for graft point),
  `solve_ik(target_pose) -> bool` (reachable?), `attach_fragment(cluster_id)`,
  `detach_fragment(at_pose)`. Plus `Pose` (position, quat xyzw) and
  `RGBDFrame` (rgb, depth in m, intrinsics fx/fy/cx/cy, `camera_to_robot` 4×4).
  The sim team implements this against Isaac Sim; we implement a mock.
- **`agent/decision_log.py`** — `DecisionLog.record(state, action, evidence,
  outcome)`; JSONL via `save()` / `load()`. Consumed by `dashboard/` and
  `cloud/debrief.py`.
- **`perception/registry.py`** — `SemanticMapEntry` (`cluster_id`,
  `species_class`, `health_status` ∈ `LIVE|DEAD|BLEACHED|TREATED|RECOVERED|NOT_RECOVERED`,
  `health_score`, `position_world`, `bounding_box_extent`,
  `optimal_graft_pose_world: GraftPose | None`, `sampled_or_restored`) and
  `SemanticSeabedRegistry` (`upsert`, `get`, `all`, `query(health_status,
  species_class)`, `dump`). `GraftPose` = position, quat, surface_normal.

## 3. What to build

### `agent/pairing.py` — donor-recipient pairing

    J(i, j) = w1*|x_rov - x_i| + w2*|x_i - x_j| - w3*H_i
    defaults: w1=1.0, w2=1.5, w3=2.0

For each unvisited `DEAD` cluster `j`, choose the `LIVE` donor `i` of the
**same species** minimising `J` (`H_i` = donor `health_score`). Pure function
over registry entries — no robot, no I/O. Weights should be easy to override
(the Argon debrief may propose changing them, e.g. "raise w3").

### `agent/graft_point.py` — PCA graft-point selector

Input: point cloud of the dead coral structure (from wrist RGB-D).

1. k-NN (k=15) normals: `scipy.spatial.cKDTree` + NumPy eigendecomposition of
   local covariance (smallest eigenvector). Skip Open3D.
2. Keep upward-facing points: `normal · [0,0,1] > 0.866` (cos 30°); prioritise
   the upper 50th-percentile height.
3. Reject points whose approach cylinder along the normal intersects
   neighbouring coral or lies outside manipulator reach.
4. Target = centroid of the largest contiguous valid patch; gripper approaches
   anti-parallel to that patch's normal. Output maps onto `GraftPose`.

### `agent/fsm.py` — `MissionFSM`

    SURVEY_SEABED -> COMPUTE_RESTORATION_PLAN -> NAVIGATE_TO_DONOR ->
    HARVEST_FRAGMENT -> NAVIGATE_TO_RECIPIENT -> TRANSPLANT_FRAGMENT
         ^                                                   |
         +------------- loop back to COMPUTE_RESTORATION_PLAN+

Loops until all restorable clusters are processed. Constructor takes a
`RobotInterface` and a `SemanticSeabedRegistry` — must behave identically
against the mock and the real sim adapter (no `isinstance` checks, no
sim-specific branches). Likely mapping onto the interface: navigate =
`set_cmd_vel` until `get_pose` is within tolerance; harvest/transplant =
`lock_base` → `get_wrist_rgbd` → graft point → `solve_ik` →
`attach_fragment` / `detach_fragment` → `unlock_base`; on success mark the
recipient `TREATED` / `sampled_or_restored=True`.

**Every transition calls `DecisionLog.record(...)` with real evidence** — the
actual pose, registry entries, `J` scores, normals, IK result, etc. that drove
the decision. No placeholder evidence (root §8).

### `eval/` test harness (owned by this branch)

- `synthetic_scene.py` — 15–20 `SemanticMapEntry` rows, 2–3 species, mixed
  LIVE/DEAD/BLEACHED, random positions in a 10×10 m seabed. Seeded by default
  (root §8: deterministic seeds, plus an unseeded "live" mode).
- `mock_robot.py` — `MockRobotInterface`: no physics, position bookkeeping,
  instant attach/detach.
- `test_fsm_loop.py` — run `MissionFSM` end-to-end on mock + synthetic scene;
  assert every BLEACHED colony ends `TREATED` and the log has evidence for every
  transition. This is **the regression test** any patch (including
  Argon-proposed ones) must pass before merge.

## 4. Definition of done

- `pytest eval/test_fsm_loop.py` passes.
- Unit test for `pairing.py`: known positions/health → expected match.
- Unit test for `graft_point.py`: synthetic cloud with a known flat upward
  patch → selector returns its centroid.
- Save a sample decision-log JSONL from a test run — the `dashboard` and
  `cloud-debrief` branches are waiting on a real one.

## 5. Rules that bite this module

- **No network calls anywhere in `agent/`.** The dive loop must run with
  "nothing to phone home to". Gemma classification lives in `perception/`
  (local endpoint); Argon lives in `cloud/` between dives. The FSM consumes
  the registry, it does not call models.
- Small, tested, pure modules where possible (pairing and graft point are
  pure; the FSM is the only stateful piece).
- No API keys or secrets; nothing here should need any.
- Never fabricate output presented as live.

## 6. Behaviours from the root spec worth designing for

Not in the minimum task doc, but they score on the rubric (perception-driven
action 25%, adaptation 25%, autonomy 15%) — leave hooks for them:

- **Abstain when unsure:** don't harvest/transplant a cluster whose
  classification confidence is low; hold, re-observe, or skip, and log why.
- **Re-plan on change:** returning to `COMPUTE_RESTORATION_PLAN` each loop
  means registry updates mid-mission (new detections, a site proving
  unsuitable) naturally change the next pairing.
- **Critical failure mode (root §12):** fragment dislodged mid-carry → detect,
  return, re-acquire. Consider an abort/recovery path out of
  `NAVIGATE_TO_RECIPIENT`.
- **IK unreachable** (`solve_ik` returns False) → try next graft candidate or
  next donor, logged.
- **Episodic memory:** remember rejected sites/donors ("cluster 7 rejected:
  no valid graft patch") so the loop doesn't retry them forever.
- Metrics (root §11): optimiser vs nearest-site baseline is cheap to add given
  `pairing.py` is pure.

## 7. Known inconsistencies (flag, don't silently resolve)

- `agent/README.md` describes a Gemma-driven ~1 Hz tool-picking agent loop
  (`scan`, `goto`, `inspect`, `grasp`, …); the current spec is the classical
  6-state FSM with Gemma confined to perception. Follow the FSM spec.
- **Mission narrative:** the FSM "harvests a cutting from a LIVE donor";
  root `CLAUDE.md` §1 says prefer loose fragments of opportunity and don't cut
  healthy colonies. Same code either way; pitch story is an open team
  decision.
- **Physics:** the spec PDF says zero-G + damping, not real hydrodynamics
  (root §5). Not this branch's problem, but don't assume drag/current models
  exist in the sim adapter.
- Root §4 mentions a richer site optimiser (flow, algae risk, uncertainty
  penalty, value-of-information). The task doc's `J` is the agreed minimum;
  extensions should stay inspectable and keep the same function signature.
