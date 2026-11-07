# Task: Perception

Branch: `perception`. Touches only `perception/`, `eval/coralscapes_eval.py`,
`eval/generate_synthetic_frames.py`. Don't edit files outside these.

## What exists already (on `main`, don't recreate)

- `perception/registry.py` — `SemanticMapEntry` (the schema below) and
  `SemanticSeabedRegistry`.
- `agent/robot_interface.py` — `RGBDFrame` (`rgb`, `depth`, `intrinsics`,
  `camera_to_robot`), what your projection code receives, and `Pose`.

## Build

### `perception/projection.py`

Pixel + depth → world-frame projection:

    P_world = T_world_to_robot · T_robot_to_cam · (d · K⁻¹ · [u, v, 1]ᵀ)

Input: `(u, v)` pixel, depth `d`, camera intrinsics `K` (from
`RGBDFrame.intrinsics`), `camera_to_robot` transform, and the robot's current
world pose (`RobotInterface.get_pose()`). Output: a 3D point in world
coordinates, used to fill `SemanticMapEntry.position_world`.

### `perception/classify.py`

No training — this is Gemma (`gemma-4-31b-it`) prompted on an image crop
(zero/few-shot), not a trained classifier. **Call a locally-hosted endpoint,
not Google's cloud Interactions API** — the dive loop can't have an outbound
network dependency (`CLAUDE.md` section 8, and the judging rubric's
"operational autonomy" criterion). Input: an RGB crop around a detection.
Output: `species_class` (e.g. `acropora_cervicornis`), `health_status`
(`LIVE` / `DEAD` / `BLEACHED`), `health_score` (0.0-1.0). Keep the
prompt/parsing contract simple and typed so it's unit-testable with canned
responses — most tests shouldn't need live inference.

### `eval/coralscapes_eval.py`

Pull ~30-50 images from `EPFL-ECEO/coralscapes` (Hugging Face, Apache 2.0,
already named in `CLAUDE.md` section 6), run `classify.py` against them,
report accuracy against the dataset's labels. This is a real measured number
for the PDF's "Perception-driven action" claim — not training. Caveat
clearly: real photos vs. sim renders differ, so this measures perception
accuracy, not sim-to-real transfer.

### `eval/generate_synthetic_frames.py`

One-off script (run manually, not per test): call `gemini-nano-banana-2.1` a
handful of times for reef photos at different coral health states (vibrant
LIVE colonies, bleached/white DEAD ones), cache to `eval/fixtures/`. Used by
the dashboard branch's camera panel and your own manual `classify.py` check.
Tag everything `synthetic` in filenames/metadata — never presented as real
footage.

## Definition of done

- `classify.py` unit tests pass against canned Gemma responses.
- One manual live classification call confirmed working against a real local
  endpoint.
- `coralscapes_eval.py` runs and prints an accuracy number.
- `generate_synthetic_frames.py` produces a handful of labeled images in
  `eval/fixtures/`.
