import base64
import hashlib
import io
import json
import os
from pathlib import Path
import subprocess
import threading
import tempfile
import unittest
from unittest.mock import Mock, patch
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from reefsim.lab_server import ArchitectureAdapters, GeminiPolicy, LabError, MAX_BODY, MAX_IMAGE, MAX_TELEMETRY, make_server, validate_request, local_mission_decision


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
            adapters.plan(decision_request(requireFullStack=True))
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
        self.assertEqual(payload["chat_template_kwargs"], {"enable_thinking":False})
        self.assertEqual(payload["temperature"],0)
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

    def test_mission_planning_never_calls_argon_even_with_credentials(self):
        transport=Mock()
        argon=GeminiPolicy(api_key="test",model="gemini-4-argon",transport=transport)
        result=ArchitectureAdapters(env={},argon=argon).plan(decision_request(observation={"time":12.5}))
        self.assertEqual(result["source"],"local_planner")
        self.assertFalse(result["cloudReasoningUsed"])
        self.assertEqual(result["decision"],"abort")
        self.assertEqual(result["optimizer"]["source"],"not_configured")
        transport.assert_not_called()

    def test_bad_timestamp_and_route_fail_before_billed_request(self):
        transport = Mock()
        adapters = ArchitectureAdapters(env={}, argon=GeminiPolicy(api_key="test", transport=transport))
        for observation in ({}, {"time":True}, {"time": 1,"route":[]}, {"time": 1,"route":{"alternatives":{}}}):
            with self.assertRaises(LabError) as error:
                adapters.plan(decision_request(observation=observation))
            self.assertEqual(error.exception.status, 400)
        transport.assert_not_called()

    def test_declared_cuopt_gateway_result_forwarded_as_evidence(self):
        optimizer = {"id":"decision-1","source":"cuopt","routeMode":"direct","costs":{"direct":2},"status":"solved","requestId":"decision-1","configured":True,"objectiveCost":2,"solverStatus":"SUCCESS"}
        gateway = Mock(return_value=io.BytesIO(json.dumps(optimizer).encode()))
        argon_transport = Mock(return_value=provider_response(json.dumps({"decision":"proceed","reason":"Solver selected the declared route","routeMode":"direct"})))
        adapters = ArchitectureAdapters(env={"CUOPT_ADAPTER_URL":"https://cuopt.example/solve"}, transport=gateway,
            argon=GeminiPolicy(api_key="test", model="gemini-4-argon", transport=argon_transport))
        result = adapters.plan(decision_request(observation={"time":1,"route":{"alternatives":[{"id":"direct","points":[[0,0,0],[1,0,0]]}]}}))
        self.assertEqual(result["optimizer"]["source"], "cuopt")
        self.assertEqual(adapters.status["cuopt"], "verified_response")
        argon_transport.assert_not_called()
        self.assertEqual(result["routeMode"], "direct")

    def test_fragment_target_and_retry_provenance(self):
        estimate = {"summary":"Fragment visible on seabed", "uncertainty":"Uncalibrated", "observations":[], "fragmentVisible":True, "gripperState":"empty"}
        infer = Mock(return_value={"choices":[{"message":{"content":json.dumps(estimate)}}]})
        adapters = ArchitectureAdapters(env={}, gemma_infer=infer)
        observation = {"phase":"inspect_fragment", "cameraTargetId":"fragment-a", "perceptionRequest":{"id":"capture-1", "targetId":"fragment-a", "targetKind":"fragment", "frameTimeMin":12}}
        result = adapters.perceive({"id":"capture-1-retry-2", "observation":observation, "image":camera_image()})
        self.assertEqual(result["captureRequestId"], "capture-1")
        self.assertEqual(result["requestId"], "capture-1-retry-2")
        self.assertEqual(result["targetKind"], "fragment")
        self.assertTrue(result["fragmentVisible"])
        infer.reset_mock()
        with self.assertRaises(LabError):
            adapters.perceive({"id":"old", "observation":observation, "image":camera_image(time=11)})
        infer.assert_not_called()

    def test_full_stack_requires_perception_and_solver_before_model_call(self):
        argon = Mock(api_key="test")
        adapters = ArchitectureAdapters(env={}, argon=argon)
        with self.assertRaises(LabError) as error:
            adapters.plan(decision_request(requireFullStack=True, observation={"time":1}))
        self.assertEqual(error.exception.status,503)
        argon.decide.assert_not_called()

    def test_failed_or_nonfinite_solver_cannot_reach_argon(self):
        for optimizer in ({"source":"cuopt","id":"decision-1","routeMode":"direct","status":"TIMEOUT"},
                          {"source":"cuopt","id":"decision-1","requestId":"decision-1","routeMode":"direct","status":"solved","configured":True,"solverStatus":"SUCCESS","objectiveCost":float("nan"),"costs":{"direct":float("nan")}}):
            argon = Mock(api_key="test")
            adapters = ArchitectureAdapters(env={}, argon=argon, cuopt_solve=Mock(return_value=optimizer))
            with self.assertRaises(LabError) as error:
                adapters.plan(decision_request(observation={"time":1,"route":{"alternatives":[{"id":"direct","points":[[0,0,0],[1,0,0]]}]}}))
            self.assertEqual(error.exception.status,502)
            argon.decide.assert_not_called()

    def test_local_policy_preserves_actual_solver_choice_without_argon(self):
        optimizer = {"id":"decision-1","requestId":"decision-1","source":"cuopt","configured":True,"routeMode":"direct","objectiveCost":1,"costs":{"direct":1,"clearance":2},"status":"solved","solverStatus":"SUCCESS"}
        argon = Mock(api_key="test")
        adapters = ArchitectureAdapters(env={},argon=argon,cuopt_solve=Mock(return_value=optimizer))
        result=adapters.plan(decision_request(observation={"time":1,"route":{"alternatives":[{"id":name,"points":[[0,0,0],[1,0,0]]} for name in ("direct","clearance")]}}))
        self.assertEqual(result["routeMode"],"direct")
        self.assertEqual(result["source"],"local_planner")
        argon.decide.assert_not_called()

    def test_visual_contract_does_not_infer_biological_health(self):
        visual={"targetVisible":True,"objectKind":"coral_colony","appearance":"pale_or_bleached","confidence":.9,"visualEvidence":"Pale branching coral is visible.","uncertainty":"Viability unknown from RGB.","fragmentVisible":False,"gripperState":"empty"}
        infer=Mock(return_value={"choices":[{"message":{"content":json.dumps(visual)},"finish_reason":"stop"}]})
        adapters=ArchitectureAdapters(env={},gemma_infer=infer)
        result=adapters.perceive({"id":"frame","observation":{"phase":"inspect_recipient","targetId":"recipient-1","registryTruth":"HIDDEN_LABEL"},"image":camera_image()})
        self.assertEqual(result["visualContract"],"appearance/v1")
        self.assertEqual(result["observations"][0]["health"],"unknown")
        self.assertFalse(result["observations"][0]["viabilityKnown"])
        self.assertEqual(result["observations"][0]["confidence"],.9)
        payload=infer.call_args.args[0]
        self.assertEqual(payload["structured_outputs"]["whitespace_pattern"],"")
        self.assertNotIn("HIDDEN_LABEL",json.dumps(payload))
        self.assertNotIn("recipient-1",json.dumps(payload))

    def test_incomplete_or_contradictory_visual_response_is_rejected(self):
        visual={"targetVisible":False,"objectKind":"unknown","appearance":"unknown","confidence":.9,"visualEvidence":"Nothing identifiable.","uncertainty":"Occluded.","fragmentVisible":False,"gripperState":"unknown"}
        for finish in ("length","stop"):
            infer=Mock(return_value={"choices":[{"message":{"content":json.dumps(visual)},"finish_reason":finish}]})
            with self.assertRaises(LabError):
                ArchitectureAdapters(env={},gemma_infer=infer).perceive({"id":"f","observation":{"phase":"inspect_donor","donorId":"d"},"image":camera_image()})

    def test_tracked_image_focus_guides_pixels_without_label_leakage(self):
        visual={"targetVisible":True,"objectKind":"coral_fragment","appearance":"pigmented","confidence":.8,"visualEvidence":"A separate piece lies below open jaws.","uncertainty":"Viability unknown.","fragmentVisible":True,"gripperState":"empty"}
        infer=Mock(return_value={"choices":[{"message":{"content":json.dumps(visual)},"finish_reason":"stop"}]})
        focus={"source":"tracked_camera_projection","target":[.42,.81],"gripper":[.51,.33]}
        observation={"phase":"inspect_fragment","cameraTargetId":"SECRET_FRAGMENT_ID","registryTruth":"SECRET_HEALTH","imageFocus":focus}
        result=ArchitectureAdapters(env={},gemma_infer=infer).perceive({"id":"f","observation":observation,"image":camera_image()})
        self.assertEqual(result["inputImageFocus"],focus)
        self.assertEqual(result["inputImageSha256"],hashlib.sha256(base64.b64decode(JPEG_B64)).hexdigest())
        prompt=infer.call_args.args[0]["messages"][0]["content"][1]["text"]
        for expected in ("x=0.4200, y=0.8100","x=0.5100, y=0.3300","top-left","not detected boxes","no coral between the pads","below or behind the jaws is not being held"):
            self.assertIn(expected,prompt)
        self.assertNotIn("SECRET",prompt)
        self.assertEqual(result["confidence"],.8)
        self.assertFalse(result["viabilityKnown"])

    def test_invalid_tracked_image_focus_rejects_before_model_inference(self):
        invalid=[None,{}, {"source":"model_detection","target":[.5,.5]}, {"source":"tracked_camera_projection","target":[.5,.5],"health":"healthy"}]
        for point in ([0,1,2],[-.1,.5],[.5,1.1],[True,.5],[float("nan"),.5],[float("inf"),.5],[10**400,.5],".5,.5",None):
            invalid.append({"source":"tracked_camera_projection","target":point})
        infer=Mock()
        for focus in invalid:
            with self.subTest(focus=str(focus)[:100]):
                with self.assertRaises(LabError):
                    ArchitectureAdapters(env={},gemma_infer=infer).perceive({"id":"f","observation":{"phase":"inspect_donor","donorId":"d","imageFocus":focus},"image":camera_image()})
        infer.assert_not_called()

    def test_argon_review_is_terminal_only_and_never_returns_control(self):
        transport=Mock(return_value=provider_response(json.dumps({"summary":"Inspection uncertainty held safely.","recommendations":["Improve camera exposure and rerun the negative control."]})))
        adapters=ArchitectureAdapters(env={},argon=GeminiPolicy(api_key="test",model="gemini-4-argon",transport=transport))
        with self.assertRaises(LabError):adapters.review({"id":"r","episode":{"phase":"transport"},"transportActivity":[]})
        transport.assert_not_called()
        result=adapters.review({"id":"r","episode":{"phase":"aborted","metrics":{"placed":0}},"transportActivity":[]})
        self.assertEqual(result["source"],"argon_review")
        self.assertTrue(result["reviewOnly"])
        self.assertNotIn("decision",result)
        self.assertEqual(json.loads(transport.call_args.args[0].data)["generation_config"]["thinking_level"],"low")

    def test_argon_context_reaches_only_fresh_matched_gemma_image_as_untrusted_advice(self):
        advice = {"guidance":"Recheck the gap between both pads.", "observations":["Earlier Gemma grip was unknown."],
                  "checks":["Is a distinct piece between the pads or below them?"]}
        transport = Mock(return_value=provider_response(json.dumps({"action":"rescan", "reason":"Need a fresh matched view.", "advisoryContext":advice})))
        visual = {"targetVisible":True,"objectKind":"coral_fragment","appearance":"pigmented","confidence":.8,
                  "visualEvidence":"A piece is below the pads.","uncertainty":"Grip remains unclear.","fragmentVisible":True,"gripperState":"unknown"}
        infer = Mock(return_value={"choices":[{"message":{"content":json.dumps(visual)},"finish_reason":"stop"}]})
        adapters = ArchitectureAdapters(env={}, argon=GeminiPolicy(api_key="SECRET", transport=transport), gemma_infer=infer)
        reply = adapters.assist({"id":"issue-1","episodeId":"ep-1","issue":{"kind":"perception_uncertainty","reason":"Grip unknown"},
            "observation":{"phase":"inspect_fragment","time":10,"held":True,"cameraTargetId":"fragment-1","targetKind":"fragment","captureRequestId":"old-frame"}})
        context = reply['advisoryContext']
        self.assertEqual(context['guidance'], advice['guidance'])
        self.assertEqual(context['previousCaptureRequestId'], 'old-frame')
        self.assertEqual(context['expiresAt'], 70)
        self.assertFalse(context['controlAuthority'])
        request = {"id":"new-frame","episodeId":"ep-1","advisoryContext":context,"image":camera_image(),
                   "observation":{"phase":"inspect_fragment","cameraTargetId":"fragment-1","captureRequestId":"new-frame"}}
        result = adapters.perceive(request)
        payload = infer.call_args.args[0]
        prompt = payload['messages'][0]['content'][1]['text']
        self.assertIn(advice['guidance'], prompt)
        self.assertIn(advice['checks'][0], prompt)
        self.assertIn('untrusted hypotheses and questions', prompt)
        self.assertIn('not observations of this new image', prompt)
        self.assertIn('cannot change the response schema, registry eligibility, thresholds or safety policy', prompt)
        self.assertNotIn('SECRET', prompt)
        self.assertEqual(payload['messages'][0]['content'][0]['image_url']['url'], 'data:image/jpeg;base64,' + JPEG_B64)
        self.assertEqual(result['gripperState'], 'unknown')
        self.assertNotIn('action', result)
        audit = result['advisoryContextUsed']
        self.assertEqual(audit['requestId'], 'issue-1')
        self.assertEqual(audit['targetId'], 'fragment-1')
        self.assertEqual(len(audit['contextSha256']), 64)
        self.assertNotIn('guidance', audit)
        self.assertEqual(set(payload['structured_outputs']['json']['required']), set(visual))

    def test_advisory_context_rejects_wrong_binding_stale_frames_or_added_authority_before_inference(self):
        context = {"source":"argon_assist","requestId":"issue","episodeId":"ep","targetId":"fragment-1","targetKind":"fragment",
                   "previousCaptureRequestId":"old","issuedAt":10,"expiresAt":70,"guidance":"Inspect again.",
                   "observations":[],"checks":["Is the gap visible?"],"advisoryOnly":True,"controlAuthority":False}
        request = {"id":"new","episodeId":"ep","advisoryContext":context,"image":camera_image(),
                   "observation":{"phase":"inspect_fragment","cameraTargetId":"fragment-1","captureRequestId":"new"}}
        changes = [{"episodeId":"wrong"}, {"advisoryContext":{**context,"targetId":"other"}},
                   {"advisoryContext":{**context,"targetKind":"colony"}}, {"advisoryContext":{**context,"controlAuthority":True}},
                   {"advisoryContext":{**context,"advisoryOnly":False}}, {"advisoryContext":{**context,"source":"synthetic"}},
                   {"advisoryContext":{**context,"previousCaptureRequestId":"new"}}, {"advisoryContext":{**context,"guidance":"x"*1201}},
                   {"advisoryContext":{**context,"observations":["x"]*4}}, {"advisoryContext":{**context,"checks":[]}},
                   {"advisoryContext":{**context,"checks":["x"*201]}}, {"advisoryContext":{**context,"confidence":1}},
                   {"advisoryContext":{**context,"issuedAt":float('nan')}}, {"advisoryContext":{**context,"expiresAt":71}},
                   {"image":camera_image(time=10)}, {"image":camera_image(time=71)}]
        infer = Mock()
        adapters = ArchitectureAdapters(env={}, gemma_infer=infer)
        for change in changes:
            with self.subTest(change=str(change)[:90]), self.assertRaises(LabError) as caught:
                adapters.perceive({**request, **change})
            self.assertEqual(caught.exception.status, 400)
        missing_episode = {k:v for k,v in request.items() if k != 'episodeId'}
        with self.assertRaises(LabError):
            adapters.perceive(missing_episode)
        infer.assert_not_called()

    def test_advisory_provider_output_is_bounded_and_legacy_action_reason_remains_valid(self):
        base = {"id":"issue","episodeId":"ep","issue":{"kind":"perception_uncertainty","reason":"Unknown"},
                "observation":{"phase":"inspect_fragment","time":10,"held":True}}
        advice = {"guidance":"Inspect gap.","observations":[],"checks":["Are both pads visible?"]}
        for value in ({**advice,"checks":[]}, {**advice,"observations":["x"*241]}, {**advice,"allowedActions":["proceed"]}):
            adapter = ArchitectureAdapters(env={}, argon=GeminiPolicy(api_key="test",transport=Mock(return_value=provider_response(
                json.dumps({"action":"rescan","reason":"Inspect","advisoryContext":value})))))
            with self.assertLogs('reefsim.lab_server', level='WARNING'), self.assertRaises(LabError) as caught:
                adapter.assist(base)
            self.assertEqual(caught.exception.payload()['code'], 'argon_invalid_response')
        for output in ({"action":"rescan","reason":"Inspect"}, {"action":"rescan","reason":"Inspect","advisoryContext":advice}):
            adapter = ArchitectureAdapters(env={}, argon=GeminiPolicy(api_key="test",transport=Mock(return_value=provider_response(json.dumps(output)))))
            result = adapter.assist(base)
            self.assertEqual(result['action'], 'rescan')
            self.assertNotIn('advisoryContext', result)  # Legacy request lacks a trustworthy target/capture binding.

    def test_argon_assist_is_advisory_real_protocol_and_bounded_per_episode(self):
        transport=Mock(side_effect=lambda *_args,**_kwargs:provider_response(json.dumps({"action":"rescan","reason":"Current frame leaves the gripper gap uncertain; obtain a fresh matched view."})))
        adapters=ArchitectureAdapters(env={},argon=GeminiPolicy(api_key="test",model="gemini-4-argon",transport=transport))
        request={"id":"issue-1","episodeId":"episode-1","issue":{"kind":"perception_uncertainty","reason":"Gripper state unknown"},"observation":{"phase":"inspect_fragment","time":12.5,"held":True},"perception":{"source":"gemma","gripperState":"unknown","visualContract":"appearance/v1","viabilityKnown":False}}
        result=adapters.assist(request)
        self.assertEqual(result["source"],"argon_assist")
        self.assertEqual(result["action"],"rescan")
        self.assertTrue(result["advisoryOnly"])
        self.assertFalse(result["controlAuthority"])
        self.assertEqual(result["remainingAttempts"],2)
        self.assertEqual(result["interactionId"],"interaction-test")
        self.assertNotIn("decision",result)
        payload=json.loads(transport.call_args.args[0].data)
        self.assertEqual(payload["generation_config"]["thinking_level"],"low")
        self.assertEqual(payload["response_format"]["schema"]["properties"]["action"]["enum"],["rescan","hold","abort"])
        self.assertIn("cannot proceed",payload["system_instruction"])
        with self.assertRaises(LabError):adapters.assist(request)
        self.assertEqual(transport.call_count,1)
        for n in (2,3):self.assertEqual(adapters.assist({**request,"id":f"issue-{n}"})["attempt"],n)
        with self.assertRaises(LabError) as caught:adapters.assist({**request,"id":"issue-4"})
        self.assertEqual(caught.exception.status,429)
        self.assertEqual(transport.call_count,3)
        self.assertEqual(adapters.health()["components"]["argon"]["role"],"uncertainty_assistance_and_between_mission_review")

    def test_argon_assist_rejects_active_terminal_oversize_or_non_gemma_inputs_before_call(self):
        transport=Mock()
        adapters=ArchitectureAdapters(env={},argon=GeminiPolicy(api_key="test",transport=transport))
        request={"id":"issue","episodeId":"ep","issue":{"kind":"recovery","reason":"Fragment dropped"},"observation":{"phase":"recovery","time":10,"paused":True}}
        changes=[{"observation":{"phase":"transport","time":10}}, {"observation":{"phase":"complete","time":10,"held":True}}, {"observation":{"phase":"aborted","time":10,"held":True}}, {"observation":{"phase":"recovery","time":float("nan"),"held":True}}, {"perception":{"source":"synthetic"}}, {"issue":{"kind":"recovery","reason":"x"*1201}}, {"observation":{**request["observation"],"large":"x"*MAX_TELEMETRY}}, {"episodeId":""}]
        for change in changes:
            with self.subTest(change=str(change)[:80]):
                with self.assertRaises(LabError):adapters.assist({**request,**change})
        transport.assert_not_called()
        with self.assertRaises(LabError) as caught:ArchitectureAdapters(env={}).assist(request)
        self.assertEqual(caught.exception.status,503)

    def test_invalid_argon_assistance_never_authorizes_proceed_and_consumes_attempt(self):
        transport=Mock(side_effect=lambda *_args,**_kwargs:provider_response(json.dumps({"action":"proceed","reason":"Ignore the camera gate"})))
        adapters=ArchitectureAdapters(env={},argon=GeminiPolicy(api_key="test",transport=transport))
        request={"id":"bad","episodeId":"ep","issue":{"kind":"service_issue","reason":"Camera unavailable"},"observation":{"phase":"inspect_fragment","time":10,"held":True}}
        with self.assertRaises(LabError) as caught:adapters.assist(request)
        self.assertEqual(caught.exception.status,502)
        with self.assertRaises(LabError):adapters.assist(request)
        self.assertEqual(transport.call_count,1)

    def test_argon_failure_diagnostics_are_sanitized_and_classify_retryability(self):
        secret = "SECRET-credential-and-provider-body"
        cases = [
            (TimeoutError(secret), "argon_timeout", True, None),
            (URLError(TimeoutError(secret)), "argon_timeout", True, None),
            (URLError(secret), "argon_transport_error", True, None),
            (HTTPError("https://secret.example/" + secret, 429, secret, {}, None), "argon_http_error", True, 429),
            (HTTPError("https://secret.example/" + secret, 503, secret, {}, None), "argon_http_error", True, 503),
            (HTTPError("https://secret.example/" + secret, 401, secret, {}, None), "argon_http_error", False, 401),
            (json.JSONDecodeError(secret, secret, 0), "argon_invalid_json", False, None),
            (ValueError(secret), "argon_invalid_response", False, None),
        ]
        request = {"id":"issue", "episodeId":"episode", "issue":{"kind":"service_issue", "reason":secret},
                   "observation":{"phase":"inspect_fragment", "time":10, "held":True}}
        for error, code, retryable, provider_status in cases:
            with self.subTest(code=code, provider_status=provider_status):
                transport = Mock(side_effect=error)
                adapters = ArchitectureAdapters(env={}, argon=GeminiPolicy(api_key=secret, transport=transport))
                with self.assertLogs("reefsim.lab_server", level="WARNING") as logged:
                    with patch("reefsim.lab_server.time.perf_counter", side_effect=[100., 125.2]):
                        with self.assertRaises(LabError) as caught:
                            adapters.assist(request)
                payload = caught.exception.payload()
                self.assertEqual(caught.exception.status, 502)
                self.assertEqual(payload["code"], code)
                self.assertEqual(payload["retryable"], retryable)
                self.assertEqual(payload["elapsedMs"], 25200)
                self.assertEqual(payload.get("providerStatus"), provider_status)
                self.assertNotIn(secret, json.dumps(payload) + "".join(logged.output))
                self.assertNotIn("decision", payload)
                self.assertNotIn("action", payload)
                self.assertEqual(adapters.status["argon"], "error")
                with self.assertRaises(LabError):
                    adapters.assist(request)
                self.assertEqual(transport.call_count, 1)

    def test_assist_timeout_during_response_read_consumes_bounded_attempts(self):
        response = Mock()
        response.__enter__ = Mock(return_value=response)
        response.__exit__ = Mock(return_value=False)
        response.read.side_effect = TimeoutError("SECRET read error")
        transport = Mock(return_value=response)
        adapters = ArchitectureAdapters(env={}, argon=GeminiPolicy(api_key="test", transport=transport))
        request = {"episodeId":"ep", "issue":{"kind":"service_issue", "reason":"Camera unknown"},
                   "observation":{"phase":"inspect_fragment", "time":10, "held":True}}
        with self.assertLogs("reefsim.lab_server", level="WARNING"):
            for index in range(3):
                with self.assertRaises(LabError) as caught:
                    adapters.assist({**request, "id":f"request-{index}"})
                self.assertEqual(caught.exception.payload()["code"], "argon_timeout")
                self.assertEqual(transport.call_args.kwargs["timeout"], 25.)
        with self.assertRaises(LabError) as caught:
            adapters.assist({**request, "id":"fourth"})
        self.assertEqual(caught.exception.status, 429)
        self.assertEqual(transport.call_count, 3)

    def test_review_uses_same_sanitized_timeout_diagnostics(self):
        adapters = ArchitectureAdapters(env={}, argon=GeminiPolicy(api_key="test", transport=Mock(side_effect=TimeoutError("SECRET"))))
        with self.assertLogs("reefsim.lab_server", level="WARNING"):
            with self.assertRaises(LabError) as caught:
                adapters.review({"id":"review", "episode":{"phase":"aborted"}, "transportActivity":[]})
        self.assertEqual(caught.exception.payload()["code"], "argon_timeout")
        self.assertNotIn("SECRET", json.dumps(caught.exception.payload()))

    def test_local_policy_requires_loose_stock_registry_and_all_fresh_visual_gates(self):
        observation={"time":10,"decisionKind":"inspect","restorationMode":"loose_fragment","donorId":"d","targetId":"r","registryGroundTruth":{"pair":[{"id":"d","health":"healthy","species":"s","genet":"g"},{"id":"r","health":"bleached_alive","species":"s","genet":"g"}]},"onboardPerception":{"observations":[{"id":id,"visualContract":"appearance/v1","health":"unknown","targetVisible":True,"objectKind":"coral_colony","appearance":appearance,"confidence":.9,"viabilityKnown":False,"frameTime":9} for id,appearance in (("r","pale_or_bleached"),)]},"fragment":{"id":"f","donorId":"d","state":"available","detachedAtStart":True,"source":"scenario_permitted_loose_stock"},"retryBudget":2,"robot":{"holding":None}}
        packet={"source":"gemma","visualContract":"appearance/v1","targetVisible":True,"objectKind":"coral_fragment","appearance":"pigmented","confidence":.9,"viabilityKnown":False,"targetKind":"fragment","targetId":"f","fragmentVisible":True,"gripperState":"empty","frameTime":9}
        self.assertEqual(local_mission_decision(observation,["proceed","abort"],packet)["decision"],"proceed")
        # The handled recipient and detached stock are inspected; source
        # eligibility remains independent registry evidence, never inferred RGB.
        self.assertEqual(len(observation["onboardPerception"]["observations"]), 1)
        for fragment_change in ({"state":"attached"}, {"detachedAtStart":False}, {"source":"unknown"}, {"donorId":"other"}):
            with self.subTest(fragment=fragment_change):
                changed={**observation,"fragment":{**observation["fragment"],**fragment_change}}
                self.assertEqual(local_mission_decision(changed,["proceed","abort"],packet)["decision"],"abort")
        self.assertEqual(local_mission_decision({**observation,"fragment":{}},["proceed","abort"],packet)["decision"],"abort")
        for changed_packet in (None, {**packet,"targetId":"another-fragment"}, {**packet,"targetKind":"colony"},
                               {**packet,"appearance":"unknown"}, {**packet,"fragmentVisible":False},
                               {**packet,"gripperState":"unknown"}, {**packet,"frameTime":-200}):
            with self.subTest(packet=changed_packet):
                self.assertEqual(local_mission_decision(observation,["proceed","abort"],changed_packet)["decision"],"abort")
        recipient=observation["onboardPerception"]["observations"][0]
        for evidence in ([], [{**recipient,"appearance":"unknown"}], [{**recipient,"confidence":.69}], [{**recipient,"frameTime":-200}]):
            self.assertEqual(local_mission_decision({**observation,"onboardPerception":{"observations":evidence}},["proceed","abort"],packet)["decision"],"abort")
        for source_change in ({"health":"dead"}, {"genet":""}, {"genet":"other"}, {"species":"other"}):
            pair=observation["registryGroundTruth"]["pair"]
            changed={**observation,"registryGroundTruth":{"pair":[{**pair[0],**source_change},pair[1]]}}
            self.assertEqual(local_mission_decision(changed,["proceed","abort"],packet)["decision"],"abort")
        for change in ({"fragment":{**observation["fragment"],"state":"attached"}},{"restorationMode":"legacy_cut"},{"time":200},{"registryGroundTruth":{"pair":[]}}):
            self.assertEqual(local_mission_decision({**observation,**change},["proceed","abort"],packet)["decision"],"abort")
        self.assertEqual(local_mission_decision(observation,["proceed","abort"],{**packet,"confidence":.69})["decision"],"abort")
        self.assertEqual(local_mission_decision({**observation,"decisionKind":"uncertain"},["retry","abort"],packet)["decision"],"retry")
        self.assertEqual(local_mission_decision({**observation,"decisionKind":"uncertain","retryBudget":0},["retry","abort"],packet)["decision"],"abort")
        self.assertEqual(local_mission_decision({**observation,"decisionKind":"recover","fragment":{**observation["fragment"],"state":"dropped"}},["retry","abort"],packet)["decision"],"retry")


class LocalReadinessTests(unittest.TestCase):
    def adapter(self, *, models=None, solve_change=None, fail=False):
        def transport(request, *, timeout):
            if fail:
                raise URLError("SECRET endpoint/credential")
            if request.get_method() == "GET":
                self.assertEqual(timeout, 5)
                self.assertTrue(request.full_url.endswith('/v1/models'))
                result = {"data": [{"id": "gemma-4-E4B-it"}]} if models is None else models
            else:
                self.assertEqual(timeout, 10)
                self.assertTrue(request.full_url.endswith('/solve'))
                body = json.loads(request.data)
                self.assertEqual(body['alternatives'], [{"id":"direct", "points":[[0,0,0],[1,0,0]]}])
                result = {"id":body['id'], "requestId":body['id'], "source":"cuopt", "configured":True,
                          "model":"nvidia-cuopt", "status":"solved", "solverStatus":"SUCCESS",
                          "routeMode":"direct", "objectiveCost":1.5, "costs":{"direct":1.5}, "solverVersion":"26.10.0"}
                result.update(solve_change or {})
            return io.BytesIO(json.dumps(result).encode())
        callback = Mock(side_effect=transport)
        return ArchitectureAdapters(env={"GEMMA_BASE_URL":"https://gemma.example/v1", "GEMMA_API_KEY":"SECRET-gemma",
            "CUOPT_ADAPTER_URL":"https://solver.example/solve", "CUOPT_API_KEY":"SECRET-cuopt"}, transport=callback), callback

    def finish(self, adapter):
        thread = adapter._readiness_thread
        if thread:
            thread.join(2)
            self.assertFalse(thread.is_alive())
        return adapter.health()

    def test_explicit_warmup_checks_id_and_actual_solve_without_mission_evidence(self):
        adapter, transport = self.adapter()
        initial = adapter.health()
        self.assertFalse(initial['pipelineReady'])
        self.assertEqual(initial['components']['gemma']['readiness'], 'not_started')
        transport.assert_not_called()
        adapter.warmup({})
        result = self.finish(adapter)
        self.assertTrue(result['pipelineReady'])
        self.assertEqual(result['components']['gemma']['readinessCheck'], 'served_model_identity')
        self.assertEqual(result['components']['cuopt']['readinessCheck'], 'native_readiness_solve')
        for name in ('gemma', 'cuopt'):
            self.assertEqual(result['components'][name]['status'], 'unverified')
        self.assertEqual(result['telemetry']['receivedFrames'], 0)
        self.assertNotIn('SECRET', json.dumps(result))
        self.assertEqual(transport.call_count, 2)
        self.assertEqual(transport.call_args_list[0].args[0].get_header('Authorization'), 'Bearer SECRET-gemma')
        self.assertEqual(transport.call_args_list[1].args[0].get_header('Authorization'), 'Bearer SECRET-cuopt')
        adapter.warmup({})
        self.assertEqual(transport.call_count, 2)

    def test_bad_model_or_solver_contract_never_marks_pipeline_ready(self):
        cases = [(dict(models={'data':[{'id':'wrong-model'}]}), 'gemma'),
                 (dict(models={'data':'SECRET malformed models'}), 'gemma')]
        cases += [(dict(solve_change=change), 'cuopt') for change in (
            {'source':'local_heuristic'}, {'solverStatus':'FAILED'}, {'requestId':'stale'},
            {'model':'other_solver'}, {'configured':False}, {'objectiveCost':float('nan')},
            {'objectiveCost':True}, {'costs':{}}, {'routeMode':'undeclared'}, {'solverVersion':''})]
        for options, failed in cases:
            with self.subTest(options=options):
                adapter, _ = self.adapter(**options)
                adapter.warmup({})
                result = self.finish(adapter)
                self.assertFalse(result['pipelineReady'])
                self.assertEqual(result['components'][failed]['readiness'], 'error')
                self.assertEqual(result['components'][failed]['failureCode'], 'readiness_identity_or_contract_invalid')

    def test_unavailable_unconfigured_and_invalid_warmup_are_explicit(self):
        adapter, transport = self.adapter(fail=True)
        for body in (None, [], {'url':'https://attacker.example'}):
            with self.assertRaises(LabError):
                adapter.warmup(body)
        transport.assert_not_called()
        adapter.warmup({})
        result = self.finish(adapter)
        self.assertFalse(result['pipelineReady'])
        self.assertEqual(result['components']['gemma']['failureCode'], 'readiness_service_unavailable')
        self.assertNotIn('SECRET', json.dumps(result))
        empty = ArchitectureAdapters(env={}, transport=Mock())
        self.assertFalse(empty.warmup({})['pipelineReady'])
        self.assertEqual(empty.health()['components']['gemma']['readiness'], 'unconfigured')
        empty.transport.assert_not_called()

    def test_concurrent_warmup_does_not_duplicate_probes(self):
        adapter, transport = self.adapter()
        original = transport.side_effect
        entered, release = threading.Event(), threading.Event()
        def delayed(request, **kwargs):
            entered.set()
            self.assertTrue(release.wait(2))
            return original(request, **kwargs)
        transport.side_effect = delayed
        try:
            self.assertEqual(adapter.warmup({})['status'], 'warming')
            self.assertTrue(entered.wait(1))
            self.assertEqual(adapter.warmup({})['status'], 'warming')
            self.assertEqual(transport.call_count, 1)
        finally:
            release.set()
        self.assertTrue(self.finish(adapter)['pipelineReady'])
        self.assertEqual(transport.call_count, 2)

    def test_expiry_and_service_failure_invalidate_cached_readiness(self):
        adapter, _ = self.adapter()
        with patch('reefsim.lab_server.time.monotonic', return_value=100):
            adapter.warmup({})
            self.assertTrue(self.finish(adapter)['pipelineReady'])
        with patch('reefsim.lab_server.time.monotonic', return_value=341):
            self.assertFalse(adapter.health()['pipelineReady'])
            self.assertEqual(adapter.health()['components']['gemma']['readiness'], 'not_started')
            adapter.warmup({})
            self.assertTrue(self.finish(adapter)['pipelineReady'])
            adapter.status['gemma'] = 'error'
            self.assertFalse(adapter.health()['pipelineReady'])
            adapter.warmup({})
            self.assertTrue(self.finish(adapter)['pipelineReady'])
            self.assertEqual(adapter.status['gemma'], 'unverified')

    def test_documented_local_http_warmup_bootstraps_configured_services(self):
        adapter, _ = self.adapter()
        server = make_server(port=0, architecture=adapter)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        url = f'http://127.0.0.1:{server.server_port}'
        try:
            with urlopen(Request(url+'/api/lab/warmup', b'{}', {'Content-Type':'application/json'})) as response:
                self.assertIn(response.status, (200,202))
                self.assertIn('components', json.load(response))
            self.finish(adapter)
            with urlopen(url+'/api/lab/architecture') as response:
                self.assertTrue(json.load(response)['pipelineReady'])
        finally:
            server.shutdown()
            server.server_close()
            thread.join()


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

    def test_runtime_get_and_head_ignore_unchanged_mtime_but_assets_remain_cacheable(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            lab = root / 'web/lab'
            lab.mkdir(parents=True)
            paths = ['app.mjs', 'app.js', 'style.css', 'index.html', 'assets/mesh.bin']
            for name in paths:
                path = lab / name
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(b'old runtime bytes')
                os.utime(path, (0, 0))
            server = make_server(port=0, root=root, architecture=ArchitectureAdapters(env={}))
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            url = f'http://127.0.0.1:{server.server_port}'
            try:
                for name in paths[:-1] + ['']:
                    with self.subTest(path=name):
                        target = url + '/lab/' + name
                        with urlopen(target) as response:
                            modified = response.headers['Last-Modified']
                            self.assertEqual(response.headers['Cache-Control'], 'no-store')
                            response.read()
                        path = lab / (name or 'index.html')
                        path.write_bytes(b'new runtime bytes')
                        os.utime(path, (0, 0))
                        headers = {'If-Modified-Since':modified}
                        with urlopen(Request(target, headers=headers)) as response:
                            self.assertEqual(response.status, 200)
                            self.assertEqual(response.read(), b'new runtime bytes')
                            self.assertEqual(response.headers['Cache-Control'], 'no-store')
                        with urlopen(Request(target, method='HEAD', headers=headers)) as response:
                            self.assertEqual(response.status, 200)
                            self.assertEqual(response.headers['Cache-Control'], 'no-store')
                            self.assertEqual(int(response.headers['Content-Length']), len(b'new runtime bytes'))
                            self.assertEqual(response.read(), b'')
                asset = url + '/lab/assets/mesh.bin'
                with urlopen(asset) as response:
                    modified = response.headers['Last-Modified']
                    self.assertNotEqual(response.headers.get('Cache-Control'), 'no-store')
                    response.read()
                with self.assertRaises(HTTPError) as caught:
                    urlopen(Request(asset, headers={'If-Modified-Since':modified}))
                self.assertEqual(caught.exception.code, 304)
            finally:
                server.shutdown()
                server.server_close()
                thread.join()

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
        self.assertIn("perceptionRequest",frame)
        self.assertIn("rescan",frame)
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

    def test_assistance_error_diagnostics_cross_local_http_boundary(self):
        error = LabError(502, "Argon assistance failed; mission remains held", diagnostics={
            "code":"argon_timeout", "retryable":True, "elapsedMs":25200})
        with patch.object(ArchitectureAdapters, "call", side_effect=error):
            with self.assertRaises(HTTPError) as caught:
                urlopen(Request(self.url + "/api/lab/assist", b'{}', {"Content-Type":"application/json"}))
        self.assertEqual(caught.exception.code, 502)
        self.assertEqual(json.load(caught.exception), error.payload())

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
