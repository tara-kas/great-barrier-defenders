# sim

Isaac Sim world (USD), vehicle, sensors, hydrodynamics force model, perturbation director, streaming config.

Owner: TBD (see CLAUDE.md section 10).

Runs on the Linux/Windows RTX-class GPU host, not on your Mac. See `SETUP.md` at the repo root for how to connect as a viewer.

Suggested layout as this fills in:
- `scenes/` — USD reef scene, materials, fragment rigid bodies
- `vehicle/` — AUV URDF/USD, gripper, thruster rig
- `sensors/` — camera, depth/sonar-style rays, IMU, gripper force
- `hydrodynamics/` — buoyancy/drag/added-mass/current step callback (Isaac Sim has none of this built in)
- `director/` — perturbation injection (current surge, dislodged fragment, visibility drop, ...)
