# mission

Connects the **Python research stack's** perception, FSM and file dashboard.
`run_mission` in `runner.py` is an entry point for that stack's mock harness and
simulation adapter. It is not the current browser demo entry point. The current
Gemma E4B / Argon / cuOpt pipeline lives in `sim/pelagic`; see the
[project README](../README.md) and [system architecture](../docs/ARCHITECTURE.md).

This sits outside `agent/` because `agent/` must stay free of network code, and this is where the Gemma client meets the FSM.

This interface sketch assumes initialized robot, library and adapter hooks.

```python
from agent.base_station import BaseStation
from perception.gemma_client import GemmaClient
from mission.runner import run_mission

summary = run_mission(
    robot,                                # a RobotInterface
    GemmaClient(),
    base_station=BaseStation.load("data/moore_reef/base_station.json"),
    genet_library=library,                # list of GenetRecord
    wait=sim_step,                        # advances sim time between control ticks
    fragment_held=gripper_has_fragment,   # () -> bool
    placement_verifier=push_test,         # (Pose) -> {"stable": bool, "contact": bool, ...}
    out_dir="eval/runs/take1",
    on_step=director,                     # optional, runs between FSM steps
    revisit_observer=observe,             # optional, (entry, day) -> what a return visit finds
)
```

**Safeguards.** It refuses to start without `fragment_held` and `placement_verifier`, unless you pass `allow_unverified=True`. It refuses a Gemma endpoint that isn't on this machine, unless you pass `allow_remote_perception=True`, which is for development only.

**Genets (research algorithm).** After each survey frame, bleached colonies get a UV reading from `robot.get_uv_frame()`. The reading from the fullest view is kept and matched to the library, and the match is logged per observation. This does not establish field-validated genet identification; the browser demo uses supplied registry metadata instead.

**Perception failures.** A frame that could not be processed is logged as `survey_waypoint_failed`. Three in a row abort the mission (`FSMConfig.max_perception_failures`). A frame that processed fine and shows no coral is not a failure.

**Outputs**, rewritten after every FSM step: `registry.json`, `decisions.jsonl`, `frame.png`. `summary.json` is written at the end. FSM steps are whole transitions, so the dashboard updates per transition, not during a transit.

**Try it on the mock** (needs `GEMMA_BASE_URL`):

```
python eval/run_mock_mission.py --out eval/runs/mock
```

It prints the dashboard and debrief commands for that run. Tests: `pytest eval/test_mission.py`.

The mock command exercises integration with a configured model endpoint and a
mock robot. It is not proof of hardware operation, onboard Gemma, or field
performance. Offline tests use controlled doubles for those dependencies.
