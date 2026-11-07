import json
import threading
import unittest
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from reefsim.core import ReefSimulation
from reefsim.server import Runtime, start_server


class ServerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.runtime = Runtime(ReefSimulation())
        cls.server = start_server(cls.runtime, port=0)
        cls.url = f"http://127.0.0.1:{cls.server.server_port}"

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()

    def post(self, command, **headers):
        return urlopen(Request(self.url + "/api/command", json.dumps(command).encode(),
                               {"Content-Type": "application/json", **headers}))

    def test_state_and_static_console(self):
        with urlopen(self.url + "/api/state") as response:
            state = json.load(response)
        self.assertEqual(state["mode"], "preview")
        self.assertFalse(state["runtime"]["camera_available"])
        self.assertEqual(len(state["robots"]), 2)
        with urlopen(self.url + "/") as response:
            self.assertIn(b"<html", response.read().lower())

    def test_commands_change_authoritative_state(self):
        with self.post({"action": "set_water", "visibility": 2.3}) as response:
            self.assertTrue(json.load(response)["ok"])
        self.assertEqual(self.runtime.snapshot()["water"]["visibility"], 2.3)
        with self.post({"action": "pause"}):
            pass
        now = self.runtime.snapshot()["time"]
        self.runtime.tick(.5)
        self.assertEqual(self.runtime.snapshot()["time"], now)
        with self.post({"action": "reset"}):
            pass

    def test_bad_commands_and_cross_origin_rejected(self):
        for command in ({"action": "missing"}, ["invalid"], {"action": "set_water", "visibility": -1}):
            with self.assertRaises(HTTPError) as caught:
                self.post(command)
            self.assertEqual(caught.exception.code, 400)
        with self.assertRaises(HTTPError) as caught:
            self.post({"action": "pause"}, Origin="https://unrelated.example")
        self.assertEqual(caught.exception.code, 403)

    def test_frame_endpoint_is_actual_bytes(self):
        self.runtime.set_frame(b"\x89PNG\r\n\x1a\n", 1.)
        with urlopen(self.url + "/api/frame.png") as response:
            self.assertEqual(response.headers["Content-Type"], "image/png")
            self.assertTrue(response.read().startswith(b"\x89PNG"))
        self.runtime.frame = None

    def test_spectator_frame_and_reset_invalidate_both_cameras(self):
        self.runtime.set_frame(b"\x89PNG\r\n\x1a\n", 2.)
        self.runtime.set_overview(b"\x89PNG\r\n\x1a\n", 2.)
        with urlopen(self.url + "/api/overview.png") as response:
            self.assertEqual(response.headers["Content-Type"], "image/png")
        self.assertTrue(self.runtime.snapshot()["runtime"]["overview_available"])
        self.runtime.last_error = "previous error"
        self.runtime.command({"command": "reset"})
        self.assertFalse(self.runtime.snapshot()["runtime"]["camera_available"])
        self.assertFalse(self.runtime.snapshot()["runtime"]["overview_available"])
        self.assertIsNone(self.runtime.snapshot()["runtime"]["camera_time"])
        self.assertIsNone(self.runtime.snapshot()["runtime"]["camera_error"])


if __name__ == "__main__":
    unittest.main()
