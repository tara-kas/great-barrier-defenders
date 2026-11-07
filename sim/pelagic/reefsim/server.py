"""Local-only mission console and control API, shared by preview and Isaac."""
from __future__ import annotations

import functools
import json
import threading
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit


class Runtime:
    def __init__(self, simulation, mode="preview"):
        self.simulation = simulation
        self.mode = mode
        self.lock = threading.RLock()
        self.camera_mode = "overview"
        self.frame = None
        self.frame_time = None
        self.overview = None
        self.overview_time = None
        self.last_error = None

    def tick(self, dt):
        with self.lock:
            self.simulation.step(dt)
            return self.snapshot()

    def snapshot(self):
        with self.lock:
            state = self.simulation.snapshot()
            state["mode"] = self.mode
            state["runtime"] = {
                "renderer": "isaac_rtx" if self.mode == "isaac" else "three_preview",
                "camera_available": self.frame is not None,
                "camera_time": self.frame_time,
                "overview_available": self.overview is not None,
                "overview_time": self.overview_time,
                "camera_mode": self.camera_mode,
                "camera_error": self.last_error,
                "camera_effects": "RGB attenuation and backscatter using renderer depth",
            }
            return state

    def command(self, data):
        if not isinstance(data, dict):
            raise ValueError("Command must be an object")
        action = data.get("action", data.get("command", data.get("type", "")))
        if action == "set_camera":
            mode = data.get("mode", "overview")
            if mode not in ("overview", "rov", "top", "follow"):
                raise ValueError("Unknown camera mode")
            with self.lock:
                self.camera_mode = mode
            return {"ok": True, "camera_mode": mode}
        with self.lock:
            result = self.simulation.command(data)
            if action == "reset":
                self.frame = None
                self.frame_time = None
                self.overview = None
                self.overview_time = None
                self.last_error = None
            return result

    def set_frame(self, frame, sim_time):
        with self.lock:
            self.frame = frame
            self.frame_time = sim_time
            self.last_error = None

    def set_overview(self, frame, sim_time):
        with self.lock:
            self.overview = frame
            self.overview_time = sim_time


class MissionServer(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = True


class Handler(SimpleHTTPRequestHandler):
    extensions_map = {**SimpleHTTPRequestHandler.extensions_map,
                      ".js": "text/javascript", ".mjs": "text/javascript"}

    def __init__(self, *args, runtime, **kwargs):
        self.runtime = runtime
        super().__init__(*args, **kwargs)

    def log_message(self, format, *args):
        # Kit labels stderr as application errors. Suppress routine access logs;
        # HTTP status and structured API errors remain available to clients.
        return

    def _send(self, status, payload, content_type="application/json"):
        if content_type == "application/json":
            payload = json.dumps(payload, allow_nan=False).encode()
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        try:
            self.wfile.write(payload)
        except (BrokenPipeError, ConnectionResetError):
            pass

    def do_GET(self):
        path = urlsplit(self.path).path
        if path == "/api/state":
            return self._send(200, self.runtime.snapshot())
        if path == "/api/health":
            return self._send(200, {"ok": True, "mode": self.runtime.mode})
        if path in ("/api/frame.png", "/api/overview.png"):
            with self.runtime.lock:
                frame = self.runtime.frame if path == "/api/frame.png" else self.runtime.overview
            if frame is None:
                return self._send(404, {"error": "No Isaac camera frame available"})
            return self._send(200, frame, "image/png")
        if path.startswith("/api/"):
            return self._send(404, {"error": "Unknown endpoint"})
        super().do_GET()

    def do_POST(self):
        if urlsplit(self.path).path != "/api/command":
            return self._send(404, {"error": "Unknown endpoint"})
        # Prevent another website from driving this unauthenticated local console.
        origin = self.headers.get("Origin")
        if origin and urlsplit(origin).netloc != self.headers.get("Host"):
            return self._send(403, {"error": "Cross-origin commands are disabled"})
        try:
            length = int(self.headers.get("Content-Length", "0"))
            if not 0 < length <= 16384:
                raise ValueError("Command body must be 1–16384 bytes")
            data = json.loads(self.rfile.read(length))
            self._send(200, self.runtime.command(data))
        except (ValueError, TypeError, KeyError, OverflowError) as error:
            self._send(400, {"ok": False, "error": str(error)})


def start_server(runtime, host="127.0.0.1", port=8080, web_dir=None):
    directory = Path(web_dir) if web_dir else Path(__file__).resolve().parent.parent / "web"
    if not directory.joinpath("index.html").exists():
        raise RuntimeError(f"Console files not found in {directory}")
    factory = functools.partial(Handler, runtime=runtime, directory=str(directory))
    server = MissionServer((host, port), factory)
    thread = threading.Thread(target=server.serve_forever, daemon=True, name="reef-console")
    thread.start()
    return server
