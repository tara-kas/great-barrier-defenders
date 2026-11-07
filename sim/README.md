# sim

Isaac Sim world (USD), vehicle, sensors, hydrodynamics force model, perturbation director, streaming config.

Owner: TBD (see CLAUDE.md section 10).

Runs on the Linux/Windows RTX-class GPU host, not on your Mac. See `SETUP.md` at the repo root for how to connect as a viewer.

## Standalone Isaac Sim checkpoint

The `simulation` branch includes the existing PELAGIC reef simulator in
[`pelagic/`](pelagic/README.md). It runs offline on DGX Spark with Isaac Sim
6.0.x and records synchronized director, scout and wrist-camera views. It
includes dense healthy/bleached/dead reef regions, persistent donor cuttings,
natural-branch contact, current-responsive soft tissue, fish, and wide-area UV
approval of both recipient and donor before collection. Pickup, transport,
placement and mechanical verification use white light. The existing Spark
recording passed 98 tests, eight pre-harvest approvals and 65 geometry audits.

From the repository root:

```bash
cd sim/pelagic
python3 -m pip install -e '.[optics]'
python3 -m unittest discover -s tests -v
# Run on the Spark; ffmpeg is required for an MP4 recording.
/home/smint/isaacsim/python.sh -u scripts/render_demo.py \
  --config configs/natural_reef.json --fps 24 --max-frames 4000 \
  --samples 4 --quality 17 --output outputs/uv-detection-pip
python3 scripts/validate_demo.py outputs/uv-detection-pip
```

This checkpoint uses its own `reefsim` mission controller and analytical
perception/UV gate. It is not yet connected to `mission.runner`, Gemma,
`SemanticSeabedRegistry` or the team dashboard. It collects fragments from
living donor colonies, as requested for this demo, rather than the team's
base-station racks. Its reef layout is an artistic scene, separate from the
Moore Reef dataset. A `RobotInterface` adapter, aligned sensor packets and the
team's required `fragment_held` / `placement_verifier` callbacks remain
integration work; the existing team contracts below are preserved. Neither
biological recovery nor genotype classification from camera pixels is claimed.

Source assets and licenses are bundled; generated videos and logs are excluded
from Git. See [recording evidence](pelagic/docs/VALIDATION.md) and
[variables and assumptions](pelagic/docs/ASSUMPTIONS.md).

## Connecting to the mission

Call `run_mission` from `mission/runner.py` (see `mission/README.md`). The `RobotInterface` includes `get_uv_frame()`: an HxWx3 uint8 hull view under UV excitation, pixel-aligned with the RGB frame. Colour must follow `BANDS` in `perception/genet.py`, without saturating, because genets are decoded from the share across bands.

It also needs two functions that the interface doesn't cover, and it won't start without them:

- `fragment_held() -> bool`: is the fragment still in the gripper? This is how a dislodged fragment gets detected.
- `placement_verifier(pose) -> {"stable": bool, "contact": bool, ...}`: the post-placement current-push test. `contact` says the fragment still touches the colony.

`attach_fragment` receives a base station rack slot, and `detach_fragment` should leave the fragment touching the colony. Base station geometry should match `data/moore_reef/base_station.json`.

Pass the director as `on_step`, and a sim-stepping function as `wait`.

Suggested layout as this fills in:
- `scenes/` — USD reef scene, materials, fragment rigid bodies
- `vehicle/` — AUV URDF/USD, gripper, thruster rig
- `sensors/` — camera, depth/sonar-style rays, IMU, gripper force
- `hydrodynamics/` — buoyancy/drag/added-mass/current step callback (Isaac Sim has none of this built in)
- `director/` — perturbation injection (current surge, dislodged fragment, visibility drop, ...)
