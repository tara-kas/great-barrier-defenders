# perception

This is the Python research perception stack used by `mission/runner.py`,
not the current browser demo's appearance pipeline. Start with the
[project README](../README.md) and [system architecture](../docs/ARCHITECTURE.md).
The browser demo uses Gemma E4B hosted on remote Modal GPUs through
`sim/pelagic`; its appearance observations do not establish health or genotype.

This module turns an `RGBDFrame` + robot `Pose` into
`SemanticSeabedRegistry` entries, with evidence for the decision log. Its
experimental Gemma prompts request detection and classification through a
self-hosted OpenAI-compatible vLLM endpoint. Self-hosted does not mean offline:
a Modal endpoint requires network access; a loopback endpoint runs on the
calling machine. Neither the client nor these prompts prove onboard deployment
or validated biological classification.

```
frame ─► detect.py (Gemma: boxes) ─► classify.py (Gemma: type + health per crop)
      ─► projection.py (depth → world) ─► survey.py (associate, abstain, upsert registry)
```

| File | What it does |
|---|---|
| `projection.py` | `P_world = T_world←robot · T_robot←cam · d·K⁻¹[u,v,1]ᵀ`; `project_box` gives a robust world centre + extent from all depth pixels in a box. |
| `classify.py` | Prompt + typed parser. `species_class` ∈ `acropora_branching, acropora_table, pocillopora, stylophora, branching_other, massive_meandering, other_coral` (genus / growth form: what is visually separable). `health_status` ∈ `LIVE / BLEACHED / DEAD`, plus `health_score`, `confidence`, `is_coral`, and a one-line `evidence` string. |
| `detect.py` | Gemma returns `box_2d = [ymin, xmin, ymax, xmax]` normalised to 0-1000; parsed, clipped, de-duplicated. |
| `genet.py` | `read_signature(uv, box)` decodes the share across three UV bands; `match_genet` finds the closest same-species genet within `MATCH_MAX_DISTANCE`, else no match |
| `survey.py` | `Surveyor.survey_frame(frame, pose)`: detect → classify → project → merge with nearby clusters (0.4 m) → upsert. Abstains (writes nothing) on low confidence, not-coral, missing depth, bad output, or endpoint down. Never overwrites entries the mission already acted on (`sampled_or_restored`), and keeps `optimal_graft_pose_world`. Every observation has an `evidence()` dict for the decision log. |
| `gemma_client.py` | `GemmaClient` over `POST {GEMMA_BASE_URL}/chat/completions`, logs latency + token usage. |
| `modal_vllm.py` | Deploys vLLM serving Gemma on Modal (spends credits, so check with the Modal owner first). |

## Frame conventions the `/sim` adapter must follow

- `camera_to_robot` maps the **OpenCV optical frame** (+x right, +y down, +z forward) to the robot frame. Isaac Sim cameras look down −z with +y up, so include that flip.
- `depth` is **z-depth** (Isaac Sim `distance_to_image_plane`), in metres; NaN/inf/≤0 = no return.
- `Pose.orientation_quat` is `(x, y, z, w)`, robot → world.

## Use

The example assumes an initialized `robot` and `log` implementing the shared
interfaces.

```python
from perception.gemma_client import GemmaClient
from perception.registry import SemanticSeabedRegistry
from perception.survey import Surveyor

registry = SemanticSeabedRegistry()
surveyor = Surveyor(GemmaClient(), registry)
result = surveyor.survey_frame(robot.get_hull_rgbd(), robot.get_pose())
log.record("SURVEY_SEABED", "survey_frame", result.evidence())
```

Config in `.env`: `GEMMA_BASE_URL` (e.g. `https://<ws>--reef-gemma-serve.modal.run/v1` or `http://localhost:8000/v1`), `GEMMA_API_KEY`, `GEMMA_MODEL` (default `gemma-4-31b-it`).

The client default remains the legacy `gemma-4-31b-it` identifier. To use E4B,
set `GEMMA_MODEL=gemma-4-E4B-it` explicitly and ensure it matches the model alias
served by the endpoint. Setting a model name alone does not install its weights.
`mission/runner.py` wraps this stack for the Python FSM and checks endpoint locality.

The UV signature matcher is an experimental three-band matching algorithm;
it is not validation that RGB appearance or UV fluorescence establishes genet
identity in the field. The current browser demo uses supplied registry metadata
for species, genet and eligibility.

## Test and check

```bash
python -m pytest perception -q                         # canned responses, no network
python -m perception.classify eval/fixtures/synthetic_dead_branching_other.jpg   # one live call
python eval/coralscapes_eval.py --dry-run              # build 45 balanced real-photo crops
python eval/coralscapes_eval.py                        # accuracy vs Coralscapes labels
python eval/generate_synthetic_frames.py               # Nano Banana fixtures (already generated)
```

Limits: the Coralscapes harness evaluates real-photo crops with zero-shot
prompts when actually run against a model. The presence of the harness does
not establish an accuracy result or sim-to-real transfer. `eval/fixtures/synthetic_*` are generated images whose
labels are what we asked for, not verified ground truth.
