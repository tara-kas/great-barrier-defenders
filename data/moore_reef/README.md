# Moore Reef scenario

A 10 x 10 m patch of Moore Reef, Great Barrier Reef, after a heat stress event: 20 labelled colonies, a base station of healthy stock, and follow-up results for treated colonies.

Coordinates are local metres, with the seabed datum at z = 0 and +z up, matching `FSMConfig.survey_bounds`.

## Files

| File | Contents | Read by |
|---|---|---|
| `registry.json` | `SemanticSeabedRegistry.dump()` format, exactly the frozen contract | FSM, dashboard |
| `labels.json` | Full label per colony: registry fields plus `genet_id`, `uv_signature`, `uv_intensity`, `depth_m`, `expected_action` | evaluation, planning |
| `genets.json` | Each genet's species, reference UV signature and stock count | genet matching |
| `base_station.json` | Donor racks: slot, genet, fragments available, signature | planning |
| `frames.jsonl` | 25 survey frames: file paths, pose, intrinsics, `camera_to_robot`, labelled `objects` | perception |
| `frames/` | Per frame: `_rgb.jpg`, `_uv.jpg`, `_depth.png` (16-bit millimetres, 0 = no return) | perception |
| `crops.jsonl`, `crops/` | Best RGB and UV crop per colony, with its full label | classifier evaluation |
| `recovery_timeline.json` | Day 0, 7 and 56 results for each treated colony | return visits, dashboard |
| `scenario.json` | Site, rules and camera | everything |
| `textures/` | Colony and seabed tiles, with `manifest.json` recording each model call | renderer |

`objects` in `frames.jsonl` carry `box_xyxy` in pixels and `box_2d` as `[ymin, xmin, ymax, xmax]` on a 0-1000 scale, which is the format Gemma returns in `perception/detect.py`.

## Expected actions

| `expected_action` | Colonies | Why |
|---|---|---|
| `TREAT` | 8 | Bleached, and a UV match to an in-stock genet of the same species |
| `SKIP_NO_MATCHING_GENET` | 2 | Bleached, but that genet isn't at the base station |
| `ABSTAIN_UV_MATCH_UNCERTAIN` | 2 | Bleached, but the UV reading falls between two genets |
| `SKIP_DEAD` | 4 | Dead |
| `LEAVE` | 4 | Healthy |

Pocillopora has two genets, so matching on species alone gives wrong pairings here. A genet match needs the same species and an L1 distance of at most 0.15 between normalised signatures (`match_genet` in `eval/moore_reef.py`).

## Using it

```python
from eval.moore_reef import MooreReefRobot, build_reef

robot = MooreReefRobot()   # the mock robot, with these textures
frame = robot.get_hull_rgbd()
uv = robot.get_uv_frame()
```

Run a mission: `python eval/run_mock_mission.py --scene moore-reef`. Rebuild the dataset: `python eval/generate_moore_reef.py`. Check it: `pytest eval/test_moore_reef.py`.

`registry.json` is what the current FSM reads. Genet and UV fields are in `labels.json`, so the frozen registry contract is unchanged.
