"""Contract and file-refresh checks for the dashboard adapter."""

import json
import os
import tempfile
import threading
import unittest
from http.server import ThreadingHTTPServer
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import urlopen

from server import make_handler


class DashboardServerTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        root = Path(self.temp.name)
        self.registry = root / "registry.json"
        self.decisions = root / "decisions.jsonl"
        self.frame = root / "frame.png"
        self.registry.write_text(json.dumps([{"cluster_id": "C-01", "health_status": "DEAD", "position_world": [1, 2, -18]}]))
        self.decisions.write_text(json.dumps({"timestamp": "2026-11-07T16:00:00Z", "state": "SURVEY_SEABED", "action": "Surveyed", "evidence": {}, "outcome": "Mapped"}))
        self.frame.write_bytes(b"synthetic frame bytes")
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), make_handler(self.registry, self.decisions, self.frame, "file source"))
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.addCleanup(self.stop_server)
        self.url = f"http://127.0.0.1:{self.server.server_port}"

    def stop_server(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=2)

    def get_state(self):
        with urlopen(self.url + "/api/state") as response:
            return json.load(response)

    def test_reads_frozen_contract_and_file_updates(self):
        first = self.get_state()
        self.assertEqual(first["registry"][0]["health_status"], "DEAD")
        self.assertEqual(first["decisions"][0]["state"], "SURVEY_SEABED")

        updated = {"entries": [{"cluster_id": "C-01", "health_status": "RESTORED", "position_world": [1, 2, -18]}],
                   "detections": [{"cluster_id": "C-01", "box": [0.1, 0.2, 0.3, 0.4]}]}
        replacement = self.registry.with_suffix(".tmp")
        replacement.write_text(json.dumps(updated))
        os.replace(replacement, self.registry)
        with self.decisions.open("a") as output:
            output.write("\n" + json.dumps({"timestamp": "2026-11-07T16:01:00Z", "state": "TRANSPLANT_FRAGMENT", "action": "Placed", "evidence": {"cluster_id": "C-01"}, "outcome": "Passed"}))

        second = self.get_state()
        self.assertEqual(second["registry"][0]["health_status"], "RESTORED")
        self.assertEqual(second["detections"][0]["box"], [0.1, 0.2, 0.3, 0.4])
        self.assertEqual(len(second["decisions"]), 2)
        self.assertEqual(second["decisions"][1]["evidence"]["cluster_id"], "C-01")

    def test_bad_source_reports_error(self):
        self.registry.write_text("not json")
        with self.assertRaises(HTTPError) as error:
            urlopen(self.url + "/api/state")
        self.assertEqual(error.exception.code, 503)


if __name__ == "__main__":
    unittest.main()
