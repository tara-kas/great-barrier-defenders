# Offline reef mission on DGX Spark

The simulator in [`pelagic/`](pelagic/README.md) now runs the team's actual
`mission.runner.run_mission` / `MissionFSM` through `ReefRobotAdapter`.
This demo collects a persistent natural branch cutting from **living reef**,
checks recipient and donor with UV before harvest, detects an injected grip
slip, recovers the **same fragment**, places its tissue against a natural
recipient branch and verifies the securing joint with a measured push.
Dead colonies are excluded; successful placement means `TREATED`, not recovered.

The supported recording workflow is entirely offline on the DGX Spark with
Isaac Sim 6.0.x. The Mac receives the completed MP4, with synchronized director,
scout and wrist-camera views. No camera server or livestream is started.

## Run from the repository root

```bash
# CPU planning needs the team's requirements plus numpy/Pillow.
python3 sim/pelagic/scripts/plan_team_demo.py \
  --output sim/pelagic/outputs/team-mission-recovery
# Review RTX action milestones before the full recording.
/home/smint/isaacsim/python.sh -u sim/pelagic/scripts/render_team_demo.py \
  --trace sim/pelagic/outputs/team-mission-recovery/trace.json.gz \
  --output sim/pelagic/outputs/team-preview --preview-stills --samples 8
/home/smint/isaacsim/python.sh -u sim/pelagic/scripts/render_team_demo.py \
  --trace sim/pelagic/outputs/team-mission-recovery/trace.json.gz \
  --output sim/pelagic/outputs/team-video --fps 24 --samples 4 --quality 17
```

The output is `pelagic-team-pip.mp4`. Validate and extract review frames with
`python3 sim/pelagic/scripts/validate_team_video.py sim/pelagic/outputs/team-video`. The trace contains the actual controller
trajectory; rendering replays it without changing decisions. Playback is
accelerated during transit and is labelled accordingly. The injected loss is
a controlled test, not a claim of an unscripted disturbance.

## What is implemented and assumed

| Area | This iteration |
|---|---|
| Mission | Team FSM, semantic registry, source-aware pairing, explicit same-ID recovery, placement acceptance |
| Supply | Living colonies with individual source poses and persistent fragment IDs; legacy rack mode remains compatible |
| Cuttings | Connected sections partitioned from the actual donor scan; original geometry and UVs preserved, matched exposed cut surfaces |
| Contact | An original tissue vertex in the live branch band touches an existing recipient triangle; small adhesive saddle, no extension branch |
| Push test | 0.18 N spring-damper test; displacement, stability and continued contact checked; weak/broken fixtures fail tests |
| Physics | Reduced submerged weight/drag for loose cuttings and compliant joints; not full fluid or fracture simulation |
| Reef | Bundled Pocillopora/Acropora scans at bounded levels of detail, tissue/roughness/normal maps, clustered healthy/bleached/dead cover |
| Motion | Current-driven soft fans/polyps and fish; rigid stony skeletons remain rigid |
| Perception demo | Explicit pre-mapped synthetic registry and analytical UV gate. No inference call, no image-based species/genet claim |
| Optional Gemini | Opt-in `VisionLLM` adapter and image-review CLI; requires a credential and cloud access; see below |
| Biology | Mechanical treatment only; no instant recolouring, symbiont transfer or biological revival simulated |

The scenario includes a defined sandy recovery pocket so a fallen fragment is
not hidden inside display-only coral. The reef is an artistic environment,
not a reconstruction of Moore Reef. All provenance/licences remain bundled.

The default recording is labelled **OFFLINE DEMO PERCEPTION / NO MODEL CALL**.
The [optional Gemini adapter](../docs/simulation-gemini.md) uses an explicitly
selected low-cost model and never silently substitutes mocked inference. Its
SDK requests are tested with a mock transport; live-service validation needs
credentials. Rendered RGB-D integration with the team's visual survey pipeline
remains future work; the current pre-mapped scenario deliberately skips that
pipeline rather than pretending synthetic images were inferred by Gemini.

See [the completed recording evidence](pelagic/docs/TEAM_MISSION_VALIDATION.md).

## Verification

```bash
python3 -m pytest agent/tests perception/tests eval/test_fsm_loop.py \
  eval/test_living_reef_mission.py eval/test_reef_adapter.py sim/pelagic/tests -q
```

`report.json`, `mission/decisions.jsonl`, `mission/registry.json` and
`geometry-validation.json` provide controller, identity, push-test and USD
geometry evidence. Generated videos, traces and logs are excluded from Git.
The legacy standalone demo and its earlier recordings remain available through
`scripts/render_demo.py`; they use the original independent controller.
