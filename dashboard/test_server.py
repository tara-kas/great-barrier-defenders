"""Adapter checks for source refresh, partial failure and live frame delivery."""

import json
import os
import tempfile
import threading
import unittest
from http.server import ThreadingHTTPServer
from pathlib import Path
from urllib.request import urlopen

from server import make_handler


class DashboardServerTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        root = Path(self.temp.name)
        self.registry = root / "registry.json"
        self.decisions = root / "decisions.jsonl"
        self.frame = root / "frame.jpg"
        self.telemetry = root / "telemetry.json"
        self.detections = root / "detections.json"
        self.registry.write_text(json.dumps([{"cluster_id": "C-01", "health_status": "LIVE", "position_world": [1, 2, -18]}]))
        self.decisions.write_text(json.dumps({"timestamp": "2026-11-07T16:00:00Z", "state": "SURVEY_SEABED", "action": "Surveyed", "evidence": {}, "outcome": "Mapped"}))
        self.frame.write_bytes(b"\xff\xd8frame-one\xff\xd9")
        self.telemetry.write_text(json.dumps({"pose_world": [1, 3, -17], "battery_pct": 72, "components": {"camera": {"status": "ok"}}}))
        self.detections.write_text(json.dumps({"detections": [{"cluster_id": "C-01", "box": [0.1, 0.2, 0.3, 0.4]}]}))
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), make_handler(self.registry, self.decisions, self.frame, self.telemetry, self.detections))
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.addCleanup(self.stop_server)
        self.url = f"http://127.0.0.1:{self.server.server_port}"

    def stop_server(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=2)

    def state(self):
        with urlopen(self.url + "/api/state", timeout=2) as response:
            return json.load(response)

    def test_current_sources_and_atomic_updates(self):
        first = self.state()
        self.assertEqual(first["telemetry"]["battery_pct"], 72)
        self.assertEqual(first["detections"][0]["box"], [0.1, 0.2, 0.3, 0.4])
        self.assertTrue(first["sources"]["camera"]["available"])
        self.assertFalse(first["errors"])
        self.detections.write_text(json.dumps({"frame_updated": self.frame.stat().st_mtime, "detections": []}))
        self.assertEqual(self.state()["detection_frame_updated"], self.frame.stat().st_mtime)
        replacement = self.registry.with_suffix(".tmp")
        replacement.write_text(json.dumps({"entries": [{"cluster_id": "C-01", "health_status": "RESTORED", "position_world": [2, 3, -18]}]}))
        os.replace(replacement, self.registry)
        self.assertEqual(self.state()["registry"][0]["health_status"], "RESTORED")

    def test_malformed_registry_does_not_hide_telemetry(self):
        self.registry.write_text("not json")
        payload = self.state()
        self.assertEqual(payload["registry"], [])
        self.assertEqual(payload["telemetry"]["battery_pct"], 72)
        self.assertTrue(any(error.startswith("Registry:") for error in payload["errors"]))

    def test_frame_endpoint_reads_replaced_image(self):
        with urlopen(self.url + "/api/frame", timeout=2) as response:
            self.assertEqual(response.headers["Content-Type"], "image/jpeg")
            self.assertEqual(response.read(), b"\xff\xd8frame-one\xff\xd9")
        replacement = self.frame.with_suffix(".tmp")
        replacement.write_bytes(b"\xff\xd8frame-two\xff\xd9")
        os.replace(replacement, self.frame)
        with urlopen(self.url + "/api/frame", timeout=2) as response:
            self.assertEqual(response.read(), b"\xff\xd8frame-two\xff\xd9")

    def test_video_is_multipart_and_empty_server_has_no_observations(self):
        with urlopen(self.url + "/api/video", timeout=2) as response:
            self.assertIn("multipart/x-mixed-replace", response.headers["Content-Type"])
            self.assertEqual(response.readline(), b"--reef-frame\r\n")
            self.assertIn(b"image/jpeg", response.readline())
            length = int(response.readline().split(b":", 1)[1])
            response.readline()
            self.assertIn(b"frame-one", response.read(length))
        empty_server = ThreadingHTTPServer(("127.0.0.1", 0), make_handler())
        thread = threading.Thread(target=empty_server.serve_forever, daemon=True)
        thread.start()
        try:
            with urlopen(f"http://127.0.0.1:{empty_server.server_port}/api/state", timeout=2) as response:
                data = json.load(response)
            self.assertEqual(data["registry"], [])
            self.assertFalse(data["sources"]["camera"]["configured"])
        finally:
            empty_server.shutdown()
            empty_server.server_close()
            thread.join(timeout=2)


if __name__ == "__main__":
    unittest.main()
