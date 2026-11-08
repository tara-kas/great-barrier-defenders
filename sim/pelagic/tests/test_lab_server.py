import base64
import hashlib
import io
import json
from pathlib import Path
import subprocess
import threading
import unittest
from unittest.mock import Mock, patch
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from reefsim.lab_server import ArchitectureAdapters, GeminiPolicy, LabError, MAX_BODY, MAX_IMAGE, MAX_TELEMETRY, make_server, validate_request


# An actual 2x2 RGB JPEG generated once for this fixture; no imaging dependency.
JPEG_B64 = '/9j/4AAQSkZJRgABAQAAAQABAAD/2wBDAAgGBgcGBQgHBwcJCQgKDBQNDAsLDBkSEw8UHRofHh0aHBwgJC4nICIsIxwcKDcpLDAxNDQ0Hyc5PTgyPC4zNDL/2wBDAQkJCQwLDBgNDRgyIRwhMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjL/wAARCAACAAIDASIAAhEBAxEB/8QAHwAAAQUBAQEBAQEAAAAAAAAAAAECAwQFBgcICQoL/8QAtRAAAgEDAwIEAwUFBAQAAAF9AQIDAAQRBRIhMUEGE1FhByJxFDKBkaEII0KxwRVS0fAkM2JyggkKFhcYGRolJicoKSo0NTY3ODk6Q0RFRkdISUpTVFVWV1hZWmNkZWZnaGlqc3R1dnd4eXqDhIWGh4iJipKTlJWWl5iZmqKjpKWmp6ipqrKztLW2t7i5usLDxMXGx8jJytLT1NXW19jZ2uHi4+Tl5ufo6erx8vP09fb3+Pn6/8QAHwEAAwEBAQEBAQEBAQAAAAAAAAECAwQFBgcICQoL/8QAtREAAgECBAQDBAcFBAQAAQJ3AAECAxEEBSExBhJBUQdhcRMiMoEIFEKRobHBCSMzUvAVYnLRChYkNOEl8RcYGRomJygpKjU2Nzg5OkNERUZHSElKU1RVVldYWVpjZGVmZ2hpanN0dXZ3eHl6goOEhYaHiImKkpOUlZaXmJmaoqOkpaanqKmqsrO0tba3uLm6wsPExcbHyMnK0tPU1dbX2Nna4uPk5ebn6Onq8vP09fb3+Pn6/9oADAMBAAIRAxEAPwDAooor0D5s/9k='


def camera_image(**updates):
    return {"mimeType": "image/jpeg", "data": JPEG_B64, "camera": "tool", "time": 12.5, **updates}


def decision_request(**updates):
    return {"id": "decision-1", "observation": {"phase": "inspect", "eligible": True},
            "allowedActions": ["proceed", "abort"], **updates}


def provider_response(text='{"decision":"proceed","reason":"Pair eligibility checks passed."}', **updates):
    return io.BytesIO(json.dumps({"status": "completed", "id": "interaction-test",
                                 "steps": [{"type": "model_output", "content": [{"type": "text", "text": text}]}],
                                 "usage": {"total_tokens": 120}, **updates}).encode())


class GeminiPolicyTests(unittest.TestCase):
    def test_declared_route_suggestion_with_camera_and_fusion(self):
        reply_text = json.dumps({"decision": "proceed", "reason": "Fused sonar reports a rock ahead; use the declared clearance path.", "routeMode": "clearance"})
        transport = Mock(return_value=provider_response(reply_text))
        observation = {"route": {"alternatives": [{"id": "direct"}, {"id": "clearance"}]},
                       "sensors": {"fusion": {"source": "synthetic", "hazards": ["rock-a"]}}}
        result = GeminiPolicy(api_key="test", transport=transport).decide(decision_request(observation=observation, image=camera_image()))
        self.assertEqual(result["routeMode"], "clearance")
        payload = json.loads(transport.call_args.args[0].data)
        self.assertEqual(payload["response_format"]["schema"]["properties"]["routeMode"]["enum"], ["direct", "clearance", None])
        self.assertEqual(json.loads(payload["input"][0]["text"])["observation"], observation)

    def test_rejects_undeclared_or_invalid_route_suggestion(self):
        for route in ("clearance", "teleport", {}, True):
            response = provider_response(json.dumps({"decision": "proceed", "reason": "Route request", "routeMode": route}))
            with self.subTest(route=route), self.assertRaises(LabError) as caught:
                GeminiPolicy(api_key="test", transport=Mock(return_value=response)).decide(decision_request())
            self.assertEqual(caught.exception.status, 502)

    def test_robot_camera_and_sonar_are_real_multimodal_inputs(self):
        transport = Mock(return_value=provider_response())
        policy = GeminiPolicy(api_key="test-only", transport=transport)
        request = decision_request(image=camera_image(), observation={"sonar": {"valid": True, "ranges": [0.5, 1.2]}, "phase": "inspect"})
        reply = policy.decide(request)
        payload = json.loads(transport.call_args.args[0].data)
        self.assertEqual(payload["input"][1], {"type": "image", "mime_type": "image/jpeg", "data": JPEG_B64})
        telemetry = json.loads(payload["input"][0]["text"])
        self.assertEqual(telemetry["observation"]["sonar"]["ranges"], [0.5, 1.2])
        self.assertEqual(telemetry["cameraFrame"], {"camera": "tool", "time": 12.5, "width": 2, "height": 2})
        self.assertNotIn(JPEG_B64, payload["input"][0]["text"])
        self.assertIn("health metadata remain authoritative", payload["system_instruction"])
        self.assertEqual(reply["inputImageSha256"], hashlib.sha256(base64.b64decode(JPEG_B64)).hexdigest())
        self.assertEqual(reply["inputMode"], "robot_camera_and_sonar_telemetry")
        self.assertEqual(reply["inputCamera"], "tool")
        self.assertEqual(reply["inputImageTime"], 12.5)
        self.assertNotIn(JPEG_B64, json.dumps(reply))

    def test_rejects_invalid_image_and_dimensions_before_network(self):
        raw = bytearray(base64.b64decode(JPEG_B64))
        sof = raw.index(b"\xff\xc0")
        raw[sof + 5:sof + 7] = (769).to_bytes(2, "big")
        invalid = [None, camera_image(mimeType="image/png"), camera_image(camera="orbit"),
                   camera_image(time=float("nan")), camera_image(time=True), camera_image(time=-1),
                   camera_image(data=JPEG_B64 + "\n"), camera_image(data="data:image/jpeg;base64," + JPEG_B64),
                   camera_image(data=base64.b64encode(raw).decode()),
                   camera_image(data=base64.b64encode(base64.b64decode(JPEG_B64)[:-2]).decode()),
                   camera_image(data=base64.b64encode(b"x" * (MAX_IMAGE + 1)).decode()),
                   camera_image(extra="invalid")]
        for image in invalid:
            with self.subTest(image=str(image)[:80]):
                transport = Mock()
                with self.assertRaises(LabError) as caught:
                    GeminiPolicy(api_key="test", transport=transport).decide(decision_request(image=image))
                self.assertEqual(caught.exception.status, 400)
                transport.assert_not_called()

    def test_telemetry_bound_is_independent_of_image_allowance(self):
        with self.assertRaises(LabError) as caught:
            validate_request(decision_request(image=camera_image(), observation={"large": "x" * MAX_TELEMETRY}))
        self.assertEqual(caught.exception.status, 400)
        # Header-only dimension parser allows the supported edge dimensions.
        raw = bytearray(base64.b64decode(JPEG_B64))
        sof = raw.index(b"\xff\xc0")
        raw[sof + 5:sof + 9] = b"\x03\x00\x03\x00"
        self.assertIsNotNone(validate_request(decision_request(image=camera_image(data=base64.b64encode(raw).decode()))))

    def test_real_protocol_and_evidence_with_fake_transport(self):
        transport = Mock(return_value=provider_response())
        policy = GeminiPolicy(api_key="test-only-secret", transport=transport)
        result = policy.decide(decision_request())
        self.assertEqual(result["id"], "decision-1")
        self.assertEqual(result["source"], "gemini")
        self.assertEqual(result["decision"], "proceed")
        self.assertEqual(result["usage"], {"total_tokens": 120})
        self.assertIsNone(result["inputImageSha256"])
        self.assertEqual(result["inputMode"], "structured_telemetry")
        self.assertIsNone(result["routeMode"])
        request = transport.call_args.args[0]
        self.assertEqual(request.full_url, "https://generativelanguage.googleapis.com/v1beta/interactions")
        self.assertNotIn("test-only-secret", request.full_url)
        payload = json.loads(request.data)
        self.assertFalse(payload["store"])
        self.assertFalse(payload["stream"])
        self.assertEqual(payload["response_format"]["schema"]["properties"]["decision"]["enum"], ["proceed", "abort"])
        self.assertEqual(transport.call_args.kwargs["timeout"], 25.)

    def test_missing_credentials_never_call_transport(self):
        transport = Mock()
        policy = GeminiPolicy(api_key="", transport=transport)
        self.assertFalse(policy.health()["geminiConfigured"])
        with self.assertRaises(LabError) as caught:
            policy.decide(decision_request())
        self.assertEqual(caught.exception.status, 503)
        transport.assert_not_called()

    def test_invalid_and_unfinished_outputs_never_fallback(self):
        bad = ["not JSON", '{"decision":"retry","reason":"Not allowed here"}',
               '{"decision":"proceed","reason":""}',
               '{"decision":"proceed","reason":"fine","coordinates":[0,0,0]}',
               '{"decision":{},"reason":"fine"}']
        for text in bad:
            with self.subTest(text=text), self.assertRaises(LabError) as caught:
                GeminiPolicy(api_key="test", transport=Mock(return_value=provider_response(text))).decide(decision_request())
            self.assertEqual(caught.exception.status, 502)
        with self.assertRaises(LabError):
            GeminiPolicy(api_key="test", transport=Mock(return_value=provider_response(status="in_progress"))).decide(decision_request())

    def test_request_validation_and_nonfinite_telemetry(self):
        bad = [[], {}, decision_request(id=True), decision_request(observation=[]),
               decision_request(allowedActions=["move"]), decision_request(allowedActions=["abort", "abort"]),
               decision_request(observation={"current": float("nan")}),
               decision_request(observation={"note": "x" * MAX_BODY})]
        for value in bad:
            with self.subTest(value=str(value)[:80]), self.assertRaises(LabError) as caught:
                GeminiPolicy(api_key="test", transport=Mock()).decide(value)
            self.assertEqual(caught.exception.status, 400)

    def test_transport_error_is_sanitized(self):
        with self.assertRaises(LabError) as caught:
            GeminiPolicy(api_key="secret", transport=Mock(side_effect=URLError("secret telemetry"))).decide(decision_request())
        self.assertNotIn("secret", str(caught.exception))
        self.assertEqual(caught.exception.status, 502)

    def test_single_flight_and_rate_limit(self):
        policy = GeminiPolicy(api_key="test", transport=Mock(return_value=provider_response()))
        policy._active.acquire()
        with self.assertRaises(LabError) as caught:
            policy.decide(decision_request())
        self.assertEqual(caught.exception.status, 429)
        policy._active.release()
        policy.decide(decision_request())
        with self.assertRaises(LabError) as caught:
            policy.decide(decision_request())
        self.assertEqual(caught.exception.status, 429)


class ArchitectureAdapterTests(unittest.TestCase):
    def test_telemetry_uplink_ring_receipts_and_no_model_calls(self):
        transport = Mock()
        adapters = ArchitectureAdapters(env={}, transport=transport)
        for batch in range(61):
            frames = [{"schema":"reef-rescue-telemetry/v1","time":batch+i/5,"phase":"transit"} for i in range(5)]
            with patch("reefsim.lab_server.time.monotonic", return_value=batch+1):
                reply = adapters.receive_telemetry({"streamId":"session-1","sequence":batch,"frames":frames})
        self.assertEqual(reply["acceptedFrames"],5)
        self.assertEqual(reply["totalFrames"],305)
        self.assertEqual(reply["retainedFrames"],300)
        with patch("reefsim.lab_server.time.monotonic", return_value=62):
            self.assertEqual(adapters.telemetry_health()["lastReceivedAgeSeconds"],1)
        transport.assert_not_called()

    def test_telemetry_rejects_secrets_raw_images_replays_and_rate_excess(self):
        adapters = ArchitectureAdapters(env={})
        frame = {"schema":"reef-rescue-telemetry/v1","time":0}
        packet = {"streamId":"s","sequence":0,"frames":[frame]}
        for bad in ({**frame,"image":"raw"}, {**frame,"decision":{"apiKey":"secret"}}, {**frame,"time":float("nan")}):
            with self.assertRaises(LabError) as error:
                adapters.receive_telemetry({**packet,"frames":[bad]})
            self.assertEqual(error.exception.status,400)
        adapters.receive_telemetry(packet)
        with self.assertRaises(LabError) as error:
            adapters.receive_telemetry(packet)
        self.assertEqual(error.exception.status,400)
        with self.assertRaises(LabError) as error:
            adapters.receive_telemetry({**packet,"sequence":1,"frames":[{**frame,"time":1}]})
        self.assertEqual(error.exception.status,429)

    def test_unconfigured_services_are_explicit_and_local_safety_independent(self):
        adapters = ArchitectureAdapters(env={})
        health = adapters.health()
        self.assertFalse(health["localSafety"]["networkRequired"])
        self.assertTrue(all(c["status"] == "unconfigured" for c in health["components"].values()))
        with self.assertRaises(LabError) as error:
            adapters.perceive({"id": "frame-1", "observation": {}, "image": camera_image()})
        self.assertEqual(error.exception.status, 503)
        with self.assertRaises(LabError) as error:
            adapters.plan(decision_request())
        self.assertEqual(error.exception.status, 503)

    def test_gemma_actual_image_protocol_without_registry_health_leakage(self):
        estimate = {"summary": "Pale branching target visible", "uncertainty": "Uncalibrated model estimate", "observations": [
            {"id": "recipient-1", "health": "bleached_alive", "confidence": .8}]}
        transport = Mock(return_value=io.BytesIO(json.dumps({"choices": [{"message": {"content": json.dumps(estimate)}}]}).encode()))
        adapters = ArchitectureAdapters(env={"GEMMA_BASE_URL": "http://127.0.0.1:8000/v1", "GEMMA_DEPLOYMENT": "robot"}, transport=transport)
        result = adapters.perceive({"id": "frame-1", "observation": {"phase": "inspect_recipient", "targetId": "recipient-1", "registryTruth": "SECRET_HEALTH_LABEL"}, "image": camera_image()})
        request = transport.call_args.args[0]
        self.assertEqual(request.full_url, "http://127.0.0.1:8000/v1/chat/completions")
        payload = json.loads(request.data)
        self.assertIn(JPEG_B64, payload["messages"][0]["content"][0]["image_url"]["url"])
        self.assertNotIn("SECRET_HEALTH_LABEL", json.dumps(payload))
        self.assertEqual(result["source"], "gemma")
        self.assertEqual(result["frameTime"], 12.5)
        self.assertEqual(result["observations"], estimate["observations"])
        self.assertEqual(adapters.health()["components"]["gemma"]["status"], "verified_response")

    def test_gemma_outage_or_invalid_estimate_never_looks_like_clear_scene(self):
        for text in ('{}', '{"summary":"none","uncertainty":"none","observations":[]}', '{"summary":"x","uncertainty":"x","observations":[{"id":"other","health":"healthy","confidence":0.9}]}'):
            transport = Mock(return_value=io.BytesIO(json.dumps({"choices": [{"message": {"content": text}}]}).encode()))
            adapters = ArchitectureAdapters(env={"GEMMA_BASE_URL": "https://gemma.example/v1"}, transport=transport)
            with self.assertRaises(LabError) as error:
                adapters.perceive({"id":"f", "observation":{"phase":"inspect_donor","donorId":"donor-1"}, "image":camera_image()})
            self.assertEqual(error.exception.status, 502)
            self.assertEqual(adapters.status["gemma"], "error")

    def test_argon_exact_model_low_thinking_and_no_cuopt_fabrication(self):
        transport = Mock(return_value=provider_response())
        argon = GeminiPolicy(api_key="test", model="gemini-4-argon", thinking_level="low", transport=transport)
        adapters = ArchitectureAdapters(env={}, argon=argon)
        result = adapters.plan(decision_request(observation={"time": 12.5}))
        payload = json.loads(transport.call_args.args[0].data)
        self.assertEqual(payload["model"], "gemini-4-argon")
        self.assertEqual(payload["generation_config"]["thinking_level"], "low")
        self.assertEqual(result["source"], "argon")
        self.assertEqual(result["optimizer"]["source"], "not_configured")
        self.assertTrue(result["localSafetyRequired"])

    def test_bad_timestamp_and_route_fail_before_billed_request(self):
        transport = Mock()
        adapters = ArchitectureAdapters(env={}, argon=GeminiPolicy(api_key="test", transport=transport))
        for observation in ({}, {"time":True}, {"time": 1,"route":[]}, {"time": 1,"route":{"alternatives":{}}}):
            with self.assertRaises(LabError) as error:
                adapters.plan(decision_request(observation=observation))
            self.assertEqual(error.exception.status, 400)
        transport.assert_not_called()

    def test_declared_cuopt_gateway_result_forwarded_as_evidence(self):
        optimizer = {"id":"decision-1","source":"cuopt","routeMode":"direct","costs":{"direct":2},"status":"solved"}
        gateway = Mock(return_value=io.BytesIO(json.dumps(optimizer).encode()))
        argon_transport = Mock(return_value=provider_response())
        adapters = ArchitectureAdapters(env={"CUOPT_ADAPTER_URL":"https://cuopt.example/solve"}, transport=gateway,
            argon=GeminiPolicy(api_key="test", model="gemini-4-argon", transport=argon_transport))
        result = adapters.plan(decision_request(observation={"time":1,"route":{"alternatives":[{"id":"direct","points":[[0,0,0],[1,0,0]]}]}}))
        self.assertEqual(result["optimizer"]["source"], "cuopt")
        self.assertEqual(adapters.status["cuopt"], "verified_response")
        self.assertIn('"optimizer"', json.loads(argon_transport.call_args.args[0].data)["input"][0]["text"])


class LabHTTPTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = make_server(port=0, policy=GeminiPolicy(api_key=""), architecture=ArchitectureAdapters(env={}))
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()
        cls.url = f"http://127.0.0.1:{cls.server.server_port}"

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join()

    def post(self, data, **headers):
        return urlopen(Request(self.url + "/api/lab/decision", json.dumps(data).encode(),
                               {"Content-Type": "application/json", **headers}))

    def test_health_and_static_assets(self):
        with urlopen(self.url + "/api/lab/architecture") as response:
            self.assertEqual(json.load(response)["components"]["gemma"]["status"], "unconfigured")
        with urlopen(self.url + "/api/lab/health") as response:
            health = json.load(response)
            self.assertFalse(health["geminiConfigured"])
            self.assertEqual(health["input"], "robot_camera_and_sonar_telemetry")
        with urlopen(self.url + "/vendor/three.module.js") as response:
            self.assertEqual(response.headers["Content-Type"], "text/javascript")
            response.read()
        with urlopen(self.url + "/assets/LICENSES.md") as response:
            self.assertTrue(response.read())

    def test_actual_engine_recorder_batch_crosses_http_contract(self):
        script = """
import {ReefLab} from './web/lab/simulation.mjs';
import {TelemetryRecorder} from './web/lab/telemetry.mjs';
const sim=new ReefLab(), recorder=new TelemetryRecorder();sim.command({action:'run'});
for(let i=0;i<4;i++){sim.step(.2);recorder.sample(sim.snapshot());}
process.stdout.write(JSON.stringify({streamId:'node-contract-test',sequence:0,frames:recorder.frames}));
"""
        result = subprocess.run(["node", "--input-type=module", "-e", script], cwd=Path(__file__).resolve().parent.parent,
                                check=True, capture_output=True, text=True)
        body = result.stdout.encode()
        self.assertLess(len(body),65536)
        frame = json.loads(body)["frames"][0]
        self.assertIn("registryGroundTruth",frame)
        self.assertIn("syntheticInspection",frame)
        self.assertIn("simulationParameters",frame)
        self.assertIn("regions",frame)
        self.assertIsInstance(frame["regions"],list)
        self.assertEqual(frame["numericPrecisionDecimals"],6)
        with urlopen(Request(self.url+"/api/lab/telemetry",body,{"Content-Type":"application/json"})) as response:
            receipt=json.load(response)
        self.assertEqual(receipt["acceptedFrames"],4)
        self.assertEqual(receipt["sequence"],0)
        with urlopen(self.url+"/api/lab/architecture") as response:
            health=json.load(response)
        self.assertEqual(health["telemetry"]["receivedFrames"],4)

    def test_credential_error_is_explicit(self):
        with self.assertRaises(HTTPError) as caught:
            self.post(decision_request())
        self.assertEqual(caught.exception.code, 503)
        self.assertFalse(json.load(caught.exception)["ok"])

    def test_camera_payload_reaches_policy_and_invalid_image_is_rejected(self):
        with self.assertRaises(HTTPError) as caught:
            self.post(decision_request(image=camera_image()))
        self.assertEqual(caught.exception.code, 503)  # Valid image; key is absent.
        with self.assertRaises(HTTPError) as caught:
            self.post(decision_request(image=camera_image(data="not a JPEG")))
        self.assertEqual(caught.exception.code, 400)

    def test_cross_origin_and_rebinding_blocked(self):
        for headers in ({"Origin": "https://unrelated.example"}, {"Host": "unrelated.example"},
                        {"Sec-Fetch-Site": "cross-site"}):
            with self.subTest(headers=headers), self.assertRaises(HTTPError) as caught:
                self.post(decision_request(), **headers)
            self.assertEqual(caught.exception.code, 403)

    def test_private_files_and_traversal_not_served(self):
        for path in ("/.git/config", "/../README.md", "/assets/../README.md", "/assets/%2e%2e/README.md", "/assets/"):
            with self.subTest(path=path), self.assertRaises(HTTPError) as caught:
                urlopen(self.url + path)
            self.assertEqual(caught.exception.code, 404)


if __name__ == "__main__":
    unittest.main()
