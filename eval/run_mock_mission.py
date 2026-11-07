"""Run a full mission on the mock robot with real Gemma perception.

    python eval/run_mock_mission.py --out eval/runs/mock

Needs GEMMA_BASE_URL (see perception/gemma_client.py). Frames are mock renders,
so this checks the wiring and the live outputs, not perception accuracy.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Optional

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:  # eval/ is not a package; make `agent`, `perception`, `eval` importable
    sys.path.insert(0, str(ROOT))

from eval.mock_robot import MockRobotInterface  # noqa: E402
from eval.synthetic_scene import generate_scene  # noqa: E402
from mission.runner import run_mission  # noqa: E402
from perception.gemma_client import GemmaClient  # noqa: E402


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--out", type=Path, default=ROOT / "eval/runs/mock")
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--allow-remote-gemma", action="store_true", help="development only, e.g. Modal")
    args = parser.parse_args(argv)

    try:
        llm = GemmaClient()
    except RuntimeError as err:
        print(err, file=sys.stderr)
        return 1

    robot = MockRobotInterface(generate_scene(seed=args.seed))
    try:
        summary = run_mission(
            robot,
            llm,
            wait=robot.advance,
            fragment_held=robot.fragment_held,
            placement_verifier=robot.verify_placement,
            out_dir=args.out,
            allow_remote_perception=args.allow_remote_gemma,
        )
    except ValueError as err:
        print(err, file=sys.stderr)
        return 1

    print(f"{summary.final_state}: restored {len(summary.restored)}, unrestorable {len(summary.unrestorable)}")
    print("\nWatch it:")
    print(f"  python dashboard/server.py --registry {args.out}/registry.json "
          f"--log {args.out}/decisions.jsonl --frame {args.out}/frame.png --synthetic-frame")
    print("Debrief it:")
    print(f"  python cloud/debrief.py --log {args.out}/decisions.jsonl --html {args.out}/report.html")
    return 0 if summary.final_state == "MISSION_COMPLETE" else 1


if __name__ == "__main__":
    sys.exit(main())
