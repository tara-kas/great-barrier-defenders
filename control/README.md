# control

This directory is a placeholder; it contains no standalone controller
implementation. For the implemented system, see the [project README](../README.md)
and [system architecture](../docs/ARCHITECTURE.md).

- The browser demo's vehicle controller, carry-aware motion and reflex checks
  are in [`sim/pelagic/web/lab/simulation.mjs`](../sim/pelagic/web/lab/simulation.mjs).
- The separate Python research FSM implements navigation through
  `RobotInterface.set_cmd_vel` in [`agent/fsm.py`](../agent/fsm.py).
- The offline simulation's reduced dynamics are in
  [`sim/pelagic/reefsim/team_physics.py`](../sim/pelagic/reefsim/team_physics.py).

A deployed physical vehicle's thruster allocation, state estimation and
hardware control integration are not implemented by this directory. Simulation
controller tests do not establish those hardware capabilities.
