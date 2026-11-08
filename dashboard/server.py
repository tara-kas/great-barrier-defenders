"""Read-only file adapter for mission data and continuously updated camera frames."""
from __future__ import annotations

import argparse
import json
import time
from datetime import datetime, timezone
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parent
FRAME_TYPES = {".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".png": "image/png"}


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


def read_object(path: Path) -> dict:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"{path.name} must contain a JSON object")
    return value


def source_status(path: Path | None) -> dict:
    if path is None:
        return {"configured": False, "available": False, "updated": None, "age_s": None}
    try:
        updated = path.stat().st_mtime
        return {"configured": True, "available": True, "updated": updated, "age_s": round(max(0, time.time() - updated), 2)}
    except OSError:
        return {"configured": True, "available": False, "updated": None, "age_s": None}


def make_handler(
    registry: Path | None = None,
    decisions: Path | None = None,
    frame: Path | None = None,
    telemetry: Path | None = None,
    detections: Path | None = None,
    preview_data: bool = False,
):
    sources = {"registry": registry, "decisions": decisions, "camera": frame, "telemetry": telemetry, "detections": detections}

    class Handler(SimpleHTTPRequestHandler):
        def __init__(self, *args, **kwargs):
            static_root = ROOT / "dist" if (ROOT / "dist" / "index.html").is_file() else ROOT
            super().__init__(*args, directory=str(static_root), **kwargs)

        def log_message(self, format, *args):
            if not self.path.startswith("/api/"):
                super().log_message(format, *args)

        def send_json(self, payload: dict):
            body = json.dumps(payload).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self):
            route = urlsplit(self.path).path
            if route == "/api/video":
                return self.stream_video()
            if route == "/api/frame":
                return self.single_frame()
            if route != "/api/state":
                return super().do_GET()

            status = {name: source_status(path) for name, path in sources.items()}
            errors = []
            entries, nested_detections, log, vehicle = [], [], [], {}
            if registry and status["registry"]["available"]:
                try:
                    entries, nested_detections = read_registry(registry)
                except (OSError, ValueError, json.JSONDecodeError) as error:
                    errors.append(f"Registry: {error}")
                    status["registry"]["available"] = False
            if decisions and status["decisions"]["available"]:
                try:
                    log = read_decisions(decisions)
                except (OSError, ValueError, json.JSONDecodeError) as error:
                    errors.append(f"Decisions: {error}")
                    status["decisions"]["available"] = False
            if telemetry and status["telemetry"]["available"]:
                try:
                    vehicle = read_object(telemetry)
                except (OSError, ValueError, json.JSONDecodeError) as error:
                    errors.append(f"Telemetry: {error}")
                    status["telemetry"]["available"] = False
            observations = nested_detections
            detection_frame_updated = None
            if detections and status["detections"]["available"]:
                try:
                    data = read_object(detections)
                    observations = data.get("detections", [])
                    detection_frame_updated = data.get("frame_updated")
                    if not isinstance(observations, list):
                        raise ValueError("detections must be an array")
                except (OSError, ValueError, json.JSONDecodeError) as error:
                    errors.append(f"Detections: {error}")
                    status["detections"]["available"] = False
                    observations = []
            for name, item in status.items():
                if item["configured"] and not item["available"] and not any(error.startswith(name.title()) for error in errors):
                    errors.append(f"{name.title()} source unavailable")
            self.send_json({
                "registry": entries, "decisions": log, "detections": observations,
                "detection_frame_updated": detection_frame_updated,
                "telemetry": vehicle, "sources": status, "errors": errors,
                "preview_data": preview_data,
                "server_time": datetime.now(timezone.utc).isoformat(),
            })

        def single_frame(self):
            if frame is None or frame.suffix.lower() not in FRAME_TYPES:
                return self.send_error(404, "Camera frame not configured")
            try:
                body = frame.read_bytes()
            except OSError:
                return self.send_error(404, "Camera frame unavailable")
            self.send_response(200)
            self.send_header("Content-Type", FRAME_TYPES[frame.suffix.lower()])
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def stream_video(self):
            if frame is None or frame.suffix.lower() not in FRAME_TYPES or not frame.is_file():
                return self.send_error(404, "Camera stream unavailable")
            self.send_response(200)
            self.send_header("Content-Type", "multipart/x-mixed-replace; boundary=reef-frame")
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            last_stamp = None
            last_sent = 0.0
            try:
                while True:
                    try:
                        stamp = frame.stat().st_mtime_ns
                        if stamp != last_stamp or time.monotonic() - last_sent >= 1.0:
                            body = frame.read_bytes()
                            header = (
                                f"--reef-frame\r\nContent-Type: {FRAME_TYPES[frame.suffix.lower()]}\r\n"
                                f"Content-Length: {len(body)}\r\n\r\n"
                            ).encode("ascii")
                            self.wfile.write(header + body + b"\r\n")
                            self.wfile.flush()
                            last_stamp = stamp
                            last_sent = time.monotonic()
                    except FileNotFoundError:
                        pass
                    time.sleep(0.08)
            except (BrokenPipeError, ConnectionResetError):
                pass

    return Handler


def main() -> None:
    parser = argparse.ArgumentParser(description="Serve Reef Rescue Mission Control")
    parser.add_argument("--registry", type=Path, help="SemanticSeabedRegistry JSON dump")
    parser.add_argument("--log", type=Path, help="DecisionLog JSONL output")
    parser.add_argument("--frame", type=Path, help="JPEG or PNG file continuously replaced by the camera producer")
    parser.add_argument("--telemetry", type=Path, help="Vehicle telemetry JSON")
    parser.add_argument("--detections", type=Path, help="Current image-space detection JSON")
    parser.add_argument("--preview-data", action="store_true", help="Label connected files as test data for interface review")
    parser.add_argument("--port", type=int, default=8765)
    args = parser.parse_args()
    paths = [path.expanduser().resolve() if path else None for path in (args.registry, args.log, args.frame, args.telemetry, args.detections)]
    server = ThreadingHTTPServer(("127.0.0.1", args.port), make_handler(*paths, preview_data=args.preview_data))
    print(f"Mission Control: http://127.0.0.1:{args.port}", flush=True)
    for name, path in zip(("Registry", "Decision log", "Camera frame", "Telemetry", "Detections"), paths):
        print(f"{name}: {path or 'not configured'}", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
