# Simulation entry points

The current browser mission is under [`pelagic/`](pelagic/README.md). Start
with the [project README](../README.md) and
[system architecture](../docs/ARCHITECTURE.md) for its Gemma E4B appearance
inference on Modal, bounded Argon assistance, local policy and native cuOpt
routing. The Isaac RTX feed is an independent read-only view; it is not the
browser physics or control process.

## Separate Python research simulation

The commands below exercise `mission.runner.run_mission` / `MissionFSM`
through `ReefRobotAdapter`. This older scenario uses living-source cuttings,
synthetic UV checks, a controlled grip slip, same-fragment recovery and
mechanical placement checks. It is separate from the current loose-fragment
rescue mission. Dead colonies are excluded; placement means `TREATED`, not
biological recovery.

This offline research workflow renders on a DGX Spark with Isaac Sim 6.0.x.
It does not start the independent live-feed service. Set `ISAAC_INSTALL` to
your Isaac Sim installation directory before running its Python executable.

## Run from the repository root

```bash
# CPU planning needs the team's requirements plus numpy/Pillow.
python3 sim/pelagic/scripts/plan_team_demo.py \
  --output sim/pelagic/outputs/team-mission-recovery
# Review RTX action milestones before the full recording.
"${ISAAC_INSTALL:?Set ISAAC_INSTALL to your Isaac Sim directory}/python.sh" -u sim/pelagic/scripts/render_team_demo.py \
  --trace sim/pelagic/outputs/team-mission-recovery/trace.json.gz \
  --output sim/pelagic/outputs/team-preview --preview-stills --samples 8
"${ISAAC_INSTALL:?Set ISAAC_INSTALL to your Isaac Sim directory}/python.sh" -u sim/pelagic/scripts/render_team_demo.py \
  --trace sim/pelagic/outputs/team-mission-recovery/trace.json.gz \
  --output sim/pelagic/outputs/team-video --fps 24 --samples 4 --quality 17 --max-frames 1440 --current-review
```

The output is `reef-rescue-mission.mp4`. Pass `--current-review` to also save an eight-second `reef-rescue-current.mp4` with a fixed-camera zero-current comparison. Validate and extract review frames with
`python3 sim/pelagic/scripts/validate_team_video.py sim/pelagic/outputs/team-video`. The trace contains the actual controller
trajectory; rendering replays it without changing decisions. Playback is
accelerated during transit and is labelled accordingly. The injected loss is
a controlled test, not a claim of an unscripted disturbance.

## Research scenario implementation and assumptions

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

This research workflow is labelled **OFFLINE DEMO PERCEPTION / NO MODEL CALL**.
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
The older standalone renderer at `pelagic/scripts/render_demo.py` uses an
independent controller and is not the current browser mission entry point.
