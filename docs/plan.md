# Build the non-sim half of the ROV stack, against the new spec PDF

## Context

The repo (`great-barrier-defenders`) currently only has scaffolding (empty module
dirs + READMEs) built from `CLAUDE.md`'s high-level framing. The team has since
written a much more concrete spec: *"Autonomous Coral Restoration ROV: Agent
System Specification & 24-Hour Hackathon Plan"* (PDF). It gives an
exact JSON data schema, a 6-state FSM, two concrete algorithms (donor-recipient
pairing, PCA graft-point selection), and explicit physics/grasping shortcuts for
the 24-hour budget.

A teammate owns `/sim` (Isaac Sim world, coral spawner, ROV rig, cameras — PDF
Phase 1). The question was what the rest of the team can build **today, in
parallel, without waiting on a live sim**. Answer: everything in PDF Phases 2–4
(perception/registry, pairing + PCA, FSM) is pure algorithm work that only needs
a `RobotInterface` contract and synthetic test data — not a live Isaac Sim
connection. Phase 5 (dashboard) is the same: build it against synthetic/mock
data now, point it at the real feed once `/sim` is ready.

Gemma (`gemma-4-31b-it`) replaces the PDF's classical-CV classification step
(HSV threshold / YOLOv8) for species + health classification — this is what
makes "Gemini in a connected perception loop" real for the DeepMind prize
criteria. Argon stays as the between-dives cloud debrief/patch loop from
`CLAUDE.md` §4, unchanged.

**Two things flagged to the team, not blocking:**
1. The PDF's mission ("harvest a cutting from a healthy donor") differs from
   `CLAUDE.md` §1 ("prefer fragments of opportunity, do not cut from healthy
   colonies"). Both are real restoration techniques; the team needs one
   consistent story for the pitch script. Doesn't change which code gets
   written today (same FSM either way) — flagging as a decisions-log item.
2. The PDF explicitly says **do not** build real hydrodynamics (zero gravity +
   damping instead), which is the opposite of `CLAUDE.md` §5's "we must build
   it" stance. This is the sim-owner's call, but `CLAUDE.md` should reflect the
   simplification so they don't burn hours on Fossen physics. Worth messaging
   them directly, not just leaving it in the doc.

**On edge compute**: this isn't optional. The rubric scores "operational
autonomy" against a stated edge budget, and the Robotics slides explicitly
penalize decisions that depend on a remote service ("nothing to phone home
to"); `CLAUDE.md` §8 already bans network calls in the control loop. So the
dive loop (survey → classify → pair → FSM) must run without live internet
dependency — Gemma stays on-device/local, Argon stays confined to the
between-dives cloud loop. `gemma-4-31b-it` is not actually lightweight
(`CLAUDE.md` §13 already flags the E2B/E4B edge-size question as open); for
the demo it can run locally on the same GPU box Isaac Sim uses (or Modal,
pre-warmed) rather than a literal edge chip — `CLAUDE.md` §5 already says to
report the edge budget as a target, separately from what the demo machine
runs. `classify.py` calls a local endpoint, not the cloud Interactions
API, to keep this true structurally and not just in the PDF's prose.

## Model usage map

| Model | Where | When it's called |
|---|---|---|
| `gemma-4-31b-it` (local) | `perception/classify.py` | Every detection, during the dive loop. No network call — local endpoint. |
| `gemini-4-argon` | `cloud/debrief.py` | Once per completed mission run, after the fact — reviews the decision log, proposes a patch. |
| `gemini-nano-banana-2.1` | `eval/generate_synthetic_frames.py` | A handful of one-off calls to seed synthetic camera-feed fixtures, not per-run. |

Not used today (available later, not core to this plan): `gemini-3.8-live`
(operator voice console), `deep-research-preview-04-2026` (cited evidence for
the PDF), `antigravity-preview-09-2026` (sandboxed patch verification once
Argon is proposing patches, not just debriefing), `gemini-3.8-flash` /
`gemini-3.5-flash-lite` (no clear fast-subagent/router need yet).

## What to build

All of this lives outside `/sim` and only depends on a `RobotInterface`
abstraction + synthetic data, so it's independently testable today and just
gets "plugged in" to the real sim later.

### 1. Shared contracts (`agent/robot_interface.py`, `perception/registry.py`)
- `RobotInterface` (ABC): the methods the FSM needs from whatever drives the
  ROV — `get_pose()`, `set_cmd_vel()`, `lock_base()` / `unlock_base()`,
  `get_hull_rgbd()`, `get_wrist_rgbd()`, `solve_ik(target_pose)`,
  `attach_fragment()`, `detach_fragment()`. This is the interface the sim
  owner implements against Isaac Sim's Python API/Lula IK/Surface Gripper API
  — hand it to them as soon as it's drafted.
- `SemanticMapEntry` (dataclass/pydantic model) matching the PDF §5.1 JSON
  schema exactly (`cluster_id`, `species_class`, `health_status`,
  `health_score`, `position_world`, `bounding_box_extent`,
  `optimal_graft_pose_world`, `sampled_or_restored`), plus an in-memory
  `SemanticSeabedRegistry` (get/upsert/query-by-status-and-species).

### 2. Perception (`perception/`)
- `projection.py`: implement the pixel+depth → world-frame projection from PDF
  §5.2 (`P_world = T_world_to_robot · T_robot_to_cam · (d · K⁻¹ · [u,v,1]ᵀ)`).
- `classify.py`: no training — classification is Gemma prompted on the image
  crop (zero/few-shot), not a trained model. This is what fits a 24-hour
  budget and still counts as a real perception model, not a hardcoded
  lookup. Gemma wrapper — crop around a detection, run `gemma-4-31b-it`
  (or whatever edge variant gets confirmed) against a **locally-hosted**
  endpoint, not Google's cloud Interactions API — the dive/FSM loop can't have
  an outbound network dependency (`CLAUDE.md` §8, and the rubric's
  "operational autonomy" / "nothing to phone home to" criteria). Parse
  `species_class` / `health_status` / `health_score` out of the response. Keep
  the prompt/output contract simple and typed so `classify.py` can be
  unit-tested with canned responses, no live inference needed for most tests.

### 3. Agent / planning (`agent/`)
- `pairing.py`: the donor-recipient cost function from PDF §6.1 —
  `J(i,j) = w1*|x_rov - x_i| + w2*|x_i - x_j| - w3*H_i`, defaults
  `w1=1.0, w2=1.5, w3=2.0`. Pure function over registry entries, trivially
  unit-testable.
- `graft_point.py`: PCA graft-point selector from PDF §6.2 — k-NN (k=15,
  `scipy.spatial.cKDTree` + NumPy eigendecomposition is enough; skip Open3D
  unless there's time to spare) surface normal estimation, upward-facing
  filter (`n·[0,0,1] > 0.866`), upper-50th-percentile height filter,
  collision/reachability rejection, centroid-of-largest-patch selection.
- `fsm.py`: the 6-state `MissionFSM` from PDF §7
  (`SURVEY_SEABED → COMPUTE_RESTORATION_PLAN → NAVIGATE_TO_DONOR →
  HARVEST_FRAGMENT → NAVIGATE_TO_RECIPIENT → TRANSPLANT_FRAGMENT`, looping
  back to state 2). Takes a `RobotInterface` and the registry as dependencies
  — runs identically against the mock or the real sim adapter. Log every
  transition with the evidence that caused it (`CLAUDE.md` §8 requirement) —
  feeds both the dashboard's decision log and the Argon debrief later.

### 4. Eval / synthetic test harness (`eval/`)
- `synthetic_scene.py`: generate 15–20 synthetic coral clusters (2–3 species,
  LIVE/DEAD/BLEACHED, random positions in a 10×10m seabed) directly as
  `SemanticMapEntry` rows — this is the PDF's own "procedural coral spawner"
  idea, minus the sim rendering.
- `mock_robot.py`: a `MockRobotInterface` implementing the ABC above against
  the synthetic scene — no physics, just position bookkeeping and
  instant attach/detach, matching the PDF's "fake the water / fake the
  grabbing" philosophy.
- `test_fsm_loop.py`: pytest that runs `MissionFSM` end-to-end against the
  mock + synthetic scene, asserts every DEAD cluster ends `RESTORED` and the
  decision log has evidence for each transition. This is the regression test
  `CLAUDE.md` §8 requires before any patch (including Argon-proposed ones)
  merges.
- `coralscapes_eval.py`: pull ~30-50 images from `EPFL-ECEO/coralscapes` (HF,
  Apache 2.0, already named in `CLAUDE.md` §6), run `classify.py` against
  them, report accuracy against the dataset's labels. Not training — a real,
  measured accuracy number for the PDF's "Perception-driven action" claim,
  separate from the synthetic-scene algorithm tests above. Caveat it the same
  way `CLAUDE.md` §6 already does: real photos vs. sim renders differ, so this
  measures perception accuracy, not sim-to-real transfer.

### 5. Dashboard (`dashboard/`)
- Build the 3-panel "Mission Control" view (3D viewport placeholder / camera
  feed with detection boxes / top-down map with red-dead, green-live,
  blue-restored pins) reading from the registry + event log. Run it against
  the `eval/` synthetic data today; swapping in the live sim feed later is
  just changing the data source, not the dashboard code.
- Camera-feed panel uses the Nano Banana synthetic frames from step 6 below
  instead of a blank placeholder, so the dashboard looks real before `/sim`
  exists — each frame tagged `synthetic` on screen per `CLAUDE.md` §6.

### 6. Synthetic camera frames (`eval/generate_synthetic_frames.py`)
- One-off script, run manually (not per test run, to not burn credits/time):
  call `gemini-nano-banana-2.1` a handful of times to generate a small set of
  reef photos at different coral health states (vibrant LIVE colonies,
  bleached/white DEAD ones), cache them to disk under `eval/fixtures/`. These
  back both the dashboard's camera panel and `classify.py`'s manual
  live-inference check. Filenames/metadata marked `synthetic` throughout —
  never presented as real footage.

### 7. Cloud debrief (`cloud/debrief.py`)
- One real, logged `gemini-4-argon` call per completed mock mission run (via
  the Interactions API — this is the between-dives loop, not the dive loop, so
  a network call here is fine). Input: the decision log from
  `eval/test_fsm_loop.py`'s run (every FSM transition + the evidence behind
  it). Output: a structured debrief — what happened, which transitions look
  wrong, one concrete suggested patch (e.g. "raise `w3` so pairing favors
  healthier donors"). This is Loop B from `CLAUDE.md` §4 made real today, not
  deferred: a tiny, cheap, genuinely-useful slice (debrief only — patch
  generation / Antigravity-sandboxed verification is future work, not today's
  scope). Gives you a concrete "Argon actually ran and said something real"
  artifact to point at.

## Doc updates

- **`docs/plan.md`** (this file): committed into the repo so it's visible in
  the IDE and shareable (link, copy/paste, or PR description) without needing
  `.claude/plans` access.
- **`CLAUDE.md`**: fold the PDF's §5 (schema + projection), §6 (algorithms),
  §7 (FSM) into §4/§5 so there's one living source of truth; note Gemma now
  does classification (replacing the HSV/YOLOv8 placeholder); add the
  zero-G-plus-damping simplification to §5, replacing the "we must build
  hydrodynamics" stance; add two decisions-log entries (Gemma for
  classification; adopted the PDF's FSM/schema/algorithms as canonical) and
  one open question (harvest-from-donor vs. loose-fragment narrative, for the
  pitch).
- **`requirements.txt`**: add `numpy`, `scipy` (for the PCA k-NN).

## Verification — what you'll actually see

- `pytest eval/test_fsm_loop.py` — full mock mission against synthetic data,
  all DEAD clusters reach `RESTORED`, decision log has evidence per
  transition. Printed/saved decision log is a real artifact you can read.
- Unit tests for `pairing.py` (known positions/health scores → expected match)
  and `graft_point.py` (synthetic point cloud with a known flat upward patch →
  selector picks its centroid).
- `classify.py` tested with canned Gemma responses (no live inference needed
  for CI-speed iteration); one live local-Gemma call manually confirmed
  working before the demo.
- `python eval/generate_synthetic_frames.py` — produces a handful of cached,
  `synthetic`-labeled reef images via Nano Banana; a concrete file you can
  open and look at.
- Dashboard manually opened against `eval/synthetic_scene.py` output —
  confirms all three panels render, the camera panel shows the Nano Banana
  frames with Gemma's classification boxes overlaid, and the map updates live
  as the mock FSM run progresses.
- `python cloud/debrief.py --log <path-to-decision-log>` — one real Argon
  call, prints a structured debrief of the mock run to the terminal/a file.
  This is the concrete "Argon ran for real" proof.
