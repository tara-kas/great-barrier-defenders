#!/usr/bin/env python3
"""Serve the editable browser lab; no Isaac installation or npm is required."""
from __future__ import annotations

import argparse
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from reefsim.lab_server import make_server


def main():
    parser = argparse.ArgumentParser(description="Reef Rescue AUV editable simulation lab")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8090)
    args = parser.parse_args()
    server = make_server(args.host, args.port)
    print(f"Reef Rescue AUV lab: http://{args.host}:{server.server_port}/lab/", flush=True)
    print("Local browser demo · Gemma perception / base-station Argon + optional cuOpt adapters · local safety remains independent", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
