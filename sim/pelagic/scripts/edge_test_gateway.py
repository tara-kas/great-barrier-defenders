"""Offline readiness contract tests; no model output substitutes are deployed."""
import io
import json
import unittest
from unittest.mock import patch

from edge_gateway import EdgeAdapters


class Response(io.StringIO):
    status = 200


class EdgeHealthTests(unittest.TestCase):
    def probe(self, *, model="gemma-4-E4B-it", solve=None, unavailable=False):
        native = {"source": "cuopt", "solverStatus": "SUCCESS", "configured": True}
        native = native if solve is None else solve
        def request(req, **kwargs):
            if unavailable:
                raise TimeoutError("service down")
            body = {"data": [{"id": model}]} if req.full_url.endswith("/models") else (
                {"ready": True, "nativeWarmup": native} if ":8013/" in req.full_url else {})
            return Response(json.dumps(body))
        adapter = EdgeAdapters(env={"GEMMA_BASE_URL": "http://127.0.0.1:8012/v1",
                                    "CUOPT_ADAPTER_URL": "http://127.0.0.1:8013/solve"})
        with patch("edge_gateway.urlopen", request):
            return adapter.health()

    def test_correct_loaded_model_and_actual_native_warmup_are_ready(self):
        result = self.probe()
        self.assertTrue(result["pipelineReady"])
        self.assertEqual(result["components"]["gemma"]["status"], "unverified")
        self.assertEqual(result["components"]["cuopt"]["status"], "unverified")
        # A health response must not relabel mission evidence as verified.

    def test_wrong_loaded_model_is_not_ready(self):
        result = self.probe(model="other-model")
        self.assertFalse(result["pipelineReady"])
        self.assertFalse(result["components"]["gemma"]["ready"])

    def test_boolean_readiness_without_native_solve_is_insufficient(self):
        self.assertFalse(self.probe(solve={})["pipelineReady"])

    def test_failed_or_non_native_solve_is_not_ready(self):
        for change in ({"source": "local"}, {"solverStatus": "FAILED"}, {"configured": False}):
            native = {"source": "cuopt", "solverStatus": "SUCCESS", "configured": True, **change}
            with self.subTest(change=change):
                self.assertFalse(self.probe(solve=native)["pipelineReady"])

    def test_unreachable_services_are_not_ready(self):
        self.assertFalse(self.probe(unavailable=True)["pipelineReady"])


if __name__ == "__main__":
    unittest.main()
