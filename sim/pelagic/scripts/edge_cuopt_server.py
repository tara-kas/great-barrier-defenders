#!/usr/bin/env python3
"""Loopback-only entry point for the existing native cuOpt adapter.

Run in a CUDA container using --network host. CUOPT_API_KEY is required by the
unchanged adapter; the listener is deliberately never exposed beyond loopback.
"""
import argparse
from http.server import ThreadingHTTPServer
import json
import os
from pathlib import Path

from cuopt_route_adapter import Handler, optimize


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, default=8013)
    parser.add_argument("--warmup-output", type=Path)
    args = parser.parse_args()
    if not os.environ.get("CUOPT_API_KEY"):
        parser.error("CUOPT_API_KEY must be configured server-side")
    if not 1024 <= args.port <= 65535:
        parser.error("port must be 1024–65535")
    # Readiness follows a real native solve, not the presence of credentials.
    warmup = optimize({"id": "edge-native-warmup", "alternatives": [
        {"id": "direct", "points": [[0, 0, 0], [1, 0, 0]]},
        {"id": "clearance", "points": [[0, 0, 0], [0, 1, 0], [1, 0, 0]]}],
        "currentVector": [0, 0, 0], "fusion": {"contacts": []}})
    if args.warmup_output:
        args.warmup_output.write_text(json.dumps(warmup, indent=2) + "\n")

    class ReadyHandler(Handler):
        def do_GET(self):
            import hmac
            if not hmac.compare_digest(self.headers.get("Authorization", ""), "Bearer " + os.environ["CUOPT_API_KEY"]):
                self.send_error(403)
                return
            if self.path != "/health":
                self.send_error(404)
                return
            body = json.dumps({"ready": True, "nativeWarmup": warmup}).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

    server = ThreadingHTTPServer(("127.0.0.1", args.port), ReadyHandler)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
