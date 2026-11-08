# Hackathon work split

> **Historical task plan — not current instructions.** Original branch scopes,
> model choices and mission premises below are archival and do not constrain
> current work. See the [project README](../../README.md) and
> [system architecture](../ARCHITECTURE.md) for the implemented pipeline.

4 independent branches, each scoped to its own directory so merges don't
conflict. All 4 branch off `main` at the same commit, which already has the
shared contracts: `agent/robot_interface.py`, `agent/decision_log.py`,
`perception/registry.py` — read those first, they're what every branch builds
against.

Full context: [`docs/plan.md`](../plan.md). Project rules: [`CLAUDE.md`](../../CLAUDE.md).

| Branch | Task doc | Touches |
|---|---|---|
| `perception` | [`perception.md`](./perception.md) | `perception/`, `eval/coralscapes_eval.py`, `eval/generate_synthetic_frames.py` |
| `agent-fsm` | [`agent-fsm.md`](./agent-fsm.md) | `agent/`, `eval/synthetic_scene.py`, `eval/mock_robot.py`, `eval/test_fsm_loop.py` |
| `dashboard` | [`dashboard.md`](./dashboard.md) | `dashboard/` |
| `cloud-debrief` | [`cloud.md`](./cloud.md) | `cloud/` |

## Rules to avoid merge conflicts

- Stay inside your branch's listed files/directories. If you need something
  outside them (a contract change, a new shared dependency), flag it in the
  team chat rather than editing it directly.
- Don't touch `CLAUDE.md`, `requirements.txt`, or another branch's task doc.
  If you need a new dependency, append it to the bottom of `requirements.txt`
  and flag it — don't reorder or edit around existing lines.
- Rebase onto `main` before opening a PR; don't merge `main` into your branch.
- The `RobotInterface` / `SemanticMapEntry` / `DecisionLog` shapes are frozen
  once merged. If one doesn't fit what you need, that's a quick sync message,
  not a unilateral edit.
