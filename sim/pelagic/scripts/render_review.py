#!/usr/bin/env python3
"""Compatibility entry point for the offline ten-phase robot-camera review."""
from __future__ import annotations

import argparse
import runpy
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=ROOT / "outputs" / "review")
    parser.add_argument("--config", type=Path, default=ROOT / "configs" / "cinematic.json")
    args, extra = parser.parse_known_args()
    sys.argv = [str(ROOT / "scripts" / "render_demo.py"), "--preview-stills",
                "--output", str(args.output), "--config", str(args.config), *extra]
    runpy.run_path(str(ROOT / "scripts" / "render_demo.py"), run_name="__main__")


if __name__ == "__main__":
    main()
