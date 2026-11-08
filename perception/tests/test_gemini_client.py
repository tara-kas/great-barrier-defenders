"""All requests are mocked. No credentials or network required."""

import base64
import io
import json
from types import SimpleNamespace

import pytest
from PIL import Image

from perception import gemini_client as module
from perception.gemma_client import GemmaReply


def png(size=(32, 32)):
    out = io.BytesIO()
    Image.new("RGB", size, (100, 120, 200)).save(out, format="PNG")
    return out.getvalue()


@pytest.fixture
def setup(monkeypatch):
    calls = []
    response = SimpleNamespace(status="completed", output_text='{"status":"BLEACHED"}',
                               id="test-only", usage=SimpleNamespace(total_input_tokens=110, total_output_tokens=8))
    client = SimpleNamespace(interactions=SimpleNamespace(create=lambda **kwargs: calls.append(kwargs) or response),
                             close=lambda: None)
    monkeypatch.setattr(module, "_make_client", lambda *args: client)
    return module.GeminiClient(allow_remote=True, api_key="fake-test-key"), calls, response


def test_cloud_requires_explicit_opt_in_before_reading_credentials(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "fake-test-key")
    with pytest.raises(module.GeminiError, match="disabled"):
        module.GeminiClient()


def test_missing_credentials_is_an_error(monkeypatch):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.delenv("GOOGLE_API_KEY", raising=False)
    with pytest.raises(module.GeminiError, match="Set GEMINI_API_KEY"):
        module.GeminiClient(allow_remote=True)


def test_request_schema_input_bounds_and_token_logging(setup, caplog):
    client, calls, _ = setup
    schema = {"type": "object", "properties": {"status": {"type": "string"}}}
    with caplog.at_level("INFO"):
        result = client.ask("Inspect fixture", png((1600, 800)), schema)
    assert isinstance(result, GemmaReply)
    assert result.usage == {"total_input_tokens": 110, "total_output_tokens": 8}
    request = calls[0]
    assert request["store"] is False and request["stream"] is False
    assert request["timeout"] == 30
    assert request["response_format"] == {"type": "text", "mime_type": "application/json", "schema": schema}
    assert request["generation_config"]["max_output_tokens"] == 1024
    with Image.open(io.BytesIO(base64.b64decode(request["input"][1]["data"]))) as image:
        assert image.size == (768, 384)
    assert "total_input_tokens" in caplog.text
    assert "Inspect fixture" not in caplog.text
    assert client.last_evidence["source"] == "gemini_cloud"


@pytest.mark.parametrize("status,text,expected", [("failed", "x", "did not complete"),
                                                   ("completed", "", "no text"),
                                                   ("completed", "not json", "invalid JSON")])
def test_bad_responses_never_become_fake_detections(setup, status, text, expected):
    client, calls, response = setup
    response.status, response.output_text = status, text
    with pytest.raises(module.GeminiError, match=expected):
        client.ask("Inspect", png(), {"type": "object"})
    assert len(calls) == 1


def test_error_details_cannot_leak_credentials(setup, caplog):
    client, _, _ = setup
    def fail(**kwargs):
        raise TimeoutError("url?key=secret-test-value")
    client._client.interactions.create = fail
    with pytest.raises(module.GeminiError) as error:
        client.ask("Inspect", png())
    assert "secret-test-value" not in str(error.value) + caplog.text + json.dumps(client.last_evidence)
    assert client.last_evidence["status"] == "failed"


@pytest.mark.parametrize("prompt,data", [("x" * 12001, png()), ("Inspect", b"not PNG"), ("", png())])
def test_invalid_inputs_do_not_call_model(setup, prompt, data):
    client, calls, _ = setup
    with pytest.raises(ValueError):
        client.ask(prompt, data)
    assert calls == []


def test_cli_requires_remote_flag_before_opening_file():
    with pytest.raises(SystemExit) as error:
        module.main(["/does/not/exist.png"])
    assert error.value.code == 2


def test_actual_sdk_serializes_v1_request_with_offline_transport(monkeypatch):
    genai = pytest.importorskip("google.genai")
    httpx = pytest.importorskip("httpx")
    requests = []
    def handle(request):
        requests.append(request)
        return httpx.Response(200, json={"id": "offline-sdk-test", "status": "completed",
            "steps": [{"type": "model_output", "content": [{"type": "text", "text": '{"ok":true}'}]}],
            "usage": {"total_input_tokens": 15, "total_output_tokens": 5}})
    original = genai.Client
    def construct(**kwargs):
        kwargs["http_options"].httpx_client = httpx.Client(transport=httpx.MockTransport(handle))
        return original(**kwargs)
    monkeypatch.setattr(genai, "Client", construct)
    client = module.GeminiClient(allow_remote=True, api_key="fake-offline-sdk-test-key")
    try:
        result = client.ask("Inspect fixture", png(), {"type": "object"})
    finally:
        client.close()
    assert json.loads(result.text) == {"ok": True}
    assert len(requests) == 1
    assert requests[0].url.path == "/v1/interactions"
    assert json.loads(requests[0].content)["response_format"]["mime_type"] == "application/json"
