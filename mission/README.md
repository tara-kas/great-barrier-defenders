# mission

Connects perception, the FSM and the dashboard. `run_mission` in `runner.py` is the single entry point: the mock harness and the Isaac Sim adapter both call it.

This sits outside `agent/` because `agent/` must stay free of network code, and this is where the Gemma client meets the FSM.

```python
from mission.runner import run_mission

summary = run_mission(
    robot,                                # a RobotInterface
    GemmaClient(),
    wait=sim_step,                        # advances sim time between control ticks
    fragment_held=gripper_has_fragment,   # () -> bool
    placement_verifier=push_test,         # (Pose) -> {"stable": bool, ...}
    out_dir="eval/runs/take1",
    on_step=director,                     # optional, runs between FSM steps
)
```

**Safeguards.** It refuses to start without `fragment_held` and `placement_verifier`, unless you pass `allow_unverified=True`. It refuses a Gemma endpoint that isn't on this machine, unless you pass `allow_remote_perception=True`, which is for development only.

**Perception failures.** A frame that could not be processed is logged as `survey_waypoint_failed`. Three in a row abort the mission (`FSMConfig.max_perception_failures`). A frame that processed fine and shows no coral is not a failure.

**Outputs**, rewritten after every FSM step: `registry.json`, `decisions.jsonl`, `frame.png`. `summary.json` is written at the end. FSM steps are whole transitions, so the dashboard updates per transition, not during a transit.

**Try it on the mock** (needs `GEMMA_BASE_URL`):

```
python eval/run_mock_mission.py --out eval/runs/mock
```

It prints the dashboard and debrief commands for that run. Tests: `pytest eval/test_mission.py`.
