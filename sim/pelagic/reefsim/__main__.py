"""Run the portable mission console or a deterministic validation episode."""
from __future__ import annotations

import argparse
import json
import math
import time
from pathlib import Path

from .config import load_config
from .core import ReefSimulation
from .server import Runtime, start_server


def main():
    parser = argparse.ArgumentParser(description="Pelagic reef restoration mission")
    parser.add_argument("--config", type=Path)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8080)
    parser.add_argument("--speed", type=float, default=1.)
    parser.add_argument("--episode", type=float, metavar="SECONDS", help="Run an episode without a server")
    parser.add_argument("--output", type=Path, help="Save final state JSON")
    args = parser.parse_args()
    if not math.isfinite(args.speed) or args.speed <= 0:
        parser.error("--speed must be positive")
    simulation = ReefSimulation(load_config(args.config))
    runtime = Runtime(simulation)
    if args.episode is not None:
        if not math.isfinite(args.episode) or args.episode <= 0:
            parser.error("--episode must be positive")
        for _ in range(round(args.episode * 30)):
            runtime.tick(1 / 30)
        state = runtime.snapshot()
        if args.output:
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text(json.dumps(state, indent=2))
        print(json.dumps(state.get("metrics", {}), indent=2))
        return
    server = start_server(runtime, args.host, args.port)
    print(f"Pelagic preview: http://{args.host}:{server.server_port}", flush=True)
    print("Portable mission dynamics + WebGL preview. Launch scripts/run_isaac.py for RTX rendering.", flush=True)
    dt = 1 / 60
    try:
        while True:
            start = time.monotonic()
            # Keep numerical integration stable even when fast-forwarding.
            remaining = dt * args.speed
            while remaining > 1e-8:
                substep = min(remaining, 1 / 30)
                runtime.tick(substep)
                remaining -= substep
            time.sleep(max(0., dt - (time.monotonic() - start)))
    except KeyboardInterrupt:
        pass
    finally:
        server.shutdown()
        server.server_close()


if __name__ == "__main__":
    main()
