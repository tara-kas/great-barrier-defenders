# perception

Turns an `RGBDFrame` + robot `Pose` into `SemanticSeabedRegistry` entries, with
evidence for the decision log. Gemma does detection and classification
zero-shot (no training) via a **self-hosted** OpenAI-compatible endpoint
(vLLM), never Google's cloud API, so the dive loop has nothing to phone home to.

```
frame ─► detect.py (Gemma: boxes) ─► classify.py (Gemma: type + health per crop)
      ─► projection.py (depth → world) ─► survey.py (associate, abstain, upsert registry)
```

| File | What it does |
|---|---|
| `projection.py` | `P_world = T_world←robot · T_robot←cam · d·K⁻¹[u,v,1]ᵀ`; `project_box` gives a robust world centre + extent from all depth pixels in a box. |
| `classify.py` | Prompt + typed parser. `species_class` ∈ `acropora_branching, acropora_table, pocillopora, stylophora, branching_other, massive_meandering, other_coral` (genus / growth form: what is visually separable). `health_status` ∈ `LIVE / BLEACHED / DEAD`, plus `health_score`, `confidence`, `is_coral`, and a one-line `evidence` string. |
| `detect.py` | Gemma returns `box_2d = [ymin, xmin, ymax, xmax]` normalised to 0-1000; parsed, clipped, de-duplicated. |
| `survey.py` | `Surveyor.survey_frame(frame, pose)`: detect → classify → project → merge with nearby clusters (0.4 m) → upsert. Abstains (writes nothing) on low confidence, not-coral, missing depth, bad output, or endpoint down. Never overwrites entries the mission already acted on (`RESTORED` / `sampled_or_restored`), and keeps `optimal_graft_pose_world`. Every observation has an `evidence()` dict for the decision log. |
| `gemma_client.py` | `GemmaClient` over `POST {GEMMA_BASE_URL}/chat/completions`, logs latency + token usage. |
| `modal_vllm.py` | Deploys vLLM serving Gemma on Modal (spends credits, so check with the Modal owner first). |

## Frame conventions the `/sim` adapter must follow

- `camera_to_robot` maps the **OpenCV optical frame** (+x right, +y down, +z forward) to the robot frame. Isaac Sim cameras look down −z with +y up, so include that flip.
- `depth` is **z-depth** (Isaac Sim `distance_to_image_plane`), in metres; NaN/inf/≤0 = no return.
- `Pose.orientation_quat` is `(x, y, z, w)`, robot → world.

## Use

```python
from perception.gemma_client import GemmaClient
from perception.registry import SemanticSeabedRegistry
from perception.survey import Surveyor

surveyor = Surveyor(GemmaClient(), registry)
result = surveyor.survey_frame(robot.get_hull_rgbd(), robot.get_pose())
log.record("SURVEY_SEABED", "survey_frame", result.evidence())
```

Config in `.env`: `GEMMA_BASE_URL` (e.g. `https://<ws>--reef-gemma-serve.modal.run/v1` or `http://localhost:8000/v1`), `GEMMA_API_KEY`, `GEMMA_MODEL` (default `gemma-4-31b-it`).

## Test and check

```bash
python -m pytest perception -q                         # canned responses, no network
python -m perception.classify eval/fixtures/synthetic_dead_branching_other.png   # one live call
python eval/coralscapes_eval.py --dry-run              # build 45 balanced real-photo crops
python eval/coralscapes_eval.py                        # accuracy vs Coralscapes labels
python eval/generate_synthetic_frames.py               # Nano Banana fixtures (already generated)
```

Limits: Coralscapes numbers are real photos, zero-shot. They say nothing about
sim-to-real transfer. `eval/fixtures/synthetic_*` are generated images whose
labels are what we asked for, not verified ground truth.
