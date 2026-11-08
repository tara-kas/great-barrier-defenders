# Working in `agent/`

Follow the root [CLAUDE.md](../CLAUDE.md), [README](../README.md) and
[system architecture](../docs/ARCHITECTURE.md). Historical plans under
`docs/tasks/` describe the original work split; their branch restrictions and
old LIVE-donor/DEAD-recipient premise are not current instructions.

## Scope

This is the separate Python research FSM, not the current browser controller
in `sim/pelagic/web/lab`. Keep that distinction explicit in claims and tests.
The current browser mission rescues eligible loose fragments; the Python
research stack also supports legacy base-station and living-source scenarios.
Do not mistake those scenarios for the current mission specification.

## Contracts and implementation

Read these interfaces before changing an adapter or consumer:

- `robot_interface.py`: `RobotInterface`, `Pose`, `RGBDFrame`; camera extrinsics
  map OpenCV optical coordinates to the robot, and quaternions use xyzw.
- `decision_log.py`: transition evidence stored through `DecisionLog.record`
  and JSONL `save`/`load`; consumed by the standalone dashboard and debrief.
- `../perception/registry.py`: `SemanticMapEntry`, `GraftPose` and
  `SemanticSeabedRegistry`, including eligibility status and optional genet ID.
- `base_station.py`: inventory sources and optional persistent fragment IDs.

Pairing is a pure, inspectable cost over eligible same-genet sources and
recipients. Dead colonies are excluded. The PCA graft selector operates on
supplied geometry; geometry is not biological evidence. `fsm.py` owns state
transitions, bounded attempts, carry-aware replanning and optional recovery.

Preserve callback contracts: time stepping through `wait`, perception through
`perceiver`, possession through `fragment_held`, and placement evidence through
`placement_verifier`. Additional adapter hooks for inspection, fragment
identity, recovery and source return must be implemented and tested before
claiming those capabilities. A same-fragment recovery requires matching identity
and an independent held check. Do not substitute a new inventory item.

## Rules

- Keep `agent/` free of network and model calls. It consumes supplied evidence;
  `mission/` and `perception/` own the separate model integration.
- Do not add secrets or credentials.
- Log the actual pose, registry state, cost terms, constraints, sensor/adapter
  results and reason that caused a decision. Never present fixture responses or
  placeholders as live evidence.
- Keep simulation tests reproducible and labelled. Passing a mocked test does
  not verify a model service, installed edge model or physical vehicle.
- Keep configuration explicit and validate invalid limits. Preserve fail-safe
  behavior when perception or an adapter fails.
- Interface changes require updating affected consumers and tests together.
  Prefer small pure functions for pairing and geometry.

## Verification

Run focused tests for a change, including the FSM regression when behavior
changes:

```bash
python -m pytest agent/tests eval/test_fsm_loop.py eval/test_mission.py -q
```

For adapter or persistent-fragment changes, also run
`eval/test_reef_adapter.py` and `eval/test_living_reef_mission.py`. Model-proposed
patches receive the same review and tests as other changes; this repository does
not automatically apply or promote Argon debrief suggestions.
