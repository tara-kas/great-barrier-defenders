"""Small, dependency-free file adapter for the Mission Control dashboard.

Only reads registry dumps and decision JSONL files. The agent/control loop never
calls this server; the browser polls it, so changing a source file is enough to
refresh the display.
"""

from __future__ import annotations

import argparse
import json
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parent


def read_registry(path: Path) -> tuple[list[dict], list[dict]]:
    value = json.loads(path.read_text(encoding="utf-8"))
    detections = []
    if isinstance(value, dict):
        detections = value.get("detections", [])
        value = value.get("entries", value.get("registry", []))
    if not isinstance(value, list):
        raise ValueError("registry must be a list or an object with entries")
    return value, detections if isinstance(detections, list) else []


def read_decisions(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def make_handler(registry: Path, decisions: Path, frame: Path, mode: str):
    class Handler(SimpleHTTPRequestHandler):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, directory=str(ROOT), **kwargs)

        def log_message(self, format, *args):
            if not self.path.startswith("/api/state"):
                super().log_message(format, *args)

        def do_GET(self):
            route = urlsplit(self.path).path
            if route == "/api/frame":
                try:
                    body = frame.read_bytes()
                except OSError:
                    self.send_error(404, "Frame unavailable")
                    return
                self.send_response(200)
                self.send_header("Content-Type", "image/jpeg" if frame.suffix.lower() in {".jpg", ".jpeg"} else "image/png")
                self.send_header("Cache-Control", "no-store")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
                return
            if route != "/api/state":
                return super().do_GET()
            try:
                entries, detections = read_registry(registry)
                payload = {
                    "mode": mode,
                    "registry": entries,
                    "detections": detections,
                    "decisions": read_decisions(decisions),
                    "registry_updated": registry.stat().st_mtime,
                    "decisions_updated": decisions.stat().st_mtime,
                    "frame_updated": frame.stat().st_mtime,
                    "frame_synthetic": frame == ROOT / "assets/reef-camera-synthetic.png",
                }
                body = json.dumps(payload).encode("utf-8")
                status = 200
            except (OSError, ValueError, json.JSONDecodeError) as error:
                body = json.dumps({"error": str(error)}).encode("utf-8")
                status = 503
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

    return Handler


def main() -> None:
    parser = argparse.ArgumentParser(description="Serve Reef Rescue Mission Control")
    parser.add_argument("--registry", type=Path, default=ROOT / "demo/registry.json")
    parser.add_argument("--log", type=Path, default=ROOT / "demo/decisions.jsonl")
    parser.add_argument("--frame", type=Path, default=ROOT / "assets/reef-camera-synthetic.png")
    parser.add_argument("--port", type=int, default=8765)
    args = parser.parse_args()
    registry, decisions, frame = (path.expanduser().resolve() for path in (args.registry, args.log, args.frame))
    mode = "synthetic demo" if registry == ROOT / "demo/registry.json" and decisions == ROOT / "demo/decisions.jsonl" else "file source"
    server = ThreadingHTTPServer(("127.0.0.1", args.port), make_handler(registry, decisions, frame, mode))
    print(f"Mission Control: http://127.0.0.1:{args.port}  [{mode}]", flush=True)
    print(f"Registry: {registry}\nDecision log: {decisions}\nFrame: {frame}", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
