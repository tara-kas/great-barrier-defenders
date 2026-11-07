# sim

Isaac Sim world (USD), vehicle, sensors, hydrodynamics force model, perturbation director, streaming config.

Owner: TBD (see CLAUDE.md section 10).

Runs on the Linux/Windows RTX-class GPU host, not on your Mac. See `SETUP.md` at the repo root for how to connect as a viewer.

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
