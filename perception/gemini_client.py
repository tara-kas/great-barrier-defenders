"""Explicitly opt-in cloud image review. Never used by the offline demo by default.

Implements VisionLLM with the Google Gen AI SDK Interactions API. Errors remain
errors: this client never substitutes fixture detections or another model.
"""

from __future__ import annotations

import argparse
import base64
import hashlib
import io
import json
import logging
import math
import os
import time
from pathlib import Path
from typing import Optional

from perception.gemma_client import GemmaReply, encode_png

log = logging.getLogger(__name__)
DEFAULT_MODEL = "gemini-3.5-flash-lite"
TOKEN_FIELDS = ("total_input_tokens", "total_output_tokens", "total_thought_tokens",
                "total_cached_tokens", "total_tokens", "total_tool_use_tokens")


class GeminiError(RuntimeError):
    """Cloud review failed; callers must abstain or visibly report failure."""


def _make_client(api_key: str, timeout_s: float):
    try:
        from google import genai
        from google.genai import types
    except ImportError as err:
        raise GeminiError("Install google-genai>=2.33.0 for the optional Gemini client") from err
    return genai.Client(api_key=api_key, vertexai=False, http_options=types.HttpOptions(
        api_version="v1", timeout=round(timeout_s * 1000),
        retry_options=types.HttpRetryOptions(attempts=1),
    ))


class GeminiClient:
    """One image per request, bounded input/output and per-request HTTP timeout.

    Instantiate with allow_remote=True to authorize sending the supplied image
    to Google. Credentials are read only from arguments/environment, never files.
    The existing run_mission remote-endpoint safeguard still applies separately.
    """

    base_url = "https://generativelanguage.googleapis.com/v1"

    def __init__(self, *, allow_remote: bool = False, api_key: Optional[str] = None,
                 model: Optional[str] = None, timeout_s: float = 30,
                 max_output_tokens: int = 1024) -> None:
        if not allow_remote:
            raise GeminiError("Cloud Gemini is disabled; explicitly pass allow_remote=True")
        if not math.isfinite(timeout_s) or not 0 < timeout_s <= 120:
            raise ValueError("timeout_s must be between 0 and 120 seconds")
        if not isinstance(max_output_tokens, int) or not 1 <= max_output_tokens <= 4096:
            raise ValueError("max_output_tokens must be between 1 and 4096")
        key = api_key or os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
        if not key:
            raise GeminiError("Set GEMINI_API_KEY or GOOGLE_API_KEY to enable cloud review")
        self.model = model or os.environ.get("GEMINI_MODEL") or DEFAULT_MODEL
        self.timeout_s = float(timeout_s)
        self.max_output_tokens = max_output_tokens
        self._client = _make_client(key, self.timeout_s)
        self.last_evidence = None

    def ask(self, prompt: str, image_png: bytes, json_schema: Optional[dict] = None) -> GemmaReply:
        if not isinstance(prompt, str) or not prompt.strip() or len(prompt) > 12000:
            raise ValueError("prompt must contain 1–12000 characters")
        if not isinstance(image_png, bytes) or not image_png.startswith(b"\x89PNG\r\n\x1a\n"):
            raise ValueError("image_png must contain PNG bytes")
        if len(image_png) > 8 * 1024 * 1024:
            raise ValueError("image_png exceeds the 8 MiB input limit")
        if json_schema is not None and not isinstance(json_schema, dict):
            raise ValueError("json_schema must be an object")
        from PIL import Image
        with Image.open(io.BytesIO(image_png)) as image:
            if image.width * image.height > 16_000_000:
                raise ValueError("image exceeds the 16 megapixel input limit")
            resized = encode_png(image, max_side=768)
        request = {
            "model": self.model,
            "input": [{"type": "text", "text": prompt},
                      {"type": "image", "mime_type": "image/png", "resolution": "medium",
                       "data": base64.b64encode(resized).decode("ascii")}],
            "generation_config": {"max_output_tokens": self.max_output_tokens,
                                  "thinking_level": "minimal"},
            "store": False,
            "stream": False,
            "timeout": self.timeout_s,
        }
        if json_schema is not None:
            request["response_format"] = {"type": "text", "mime_type": "application/json", "schema": json_schema}
        started = time.perf_counter()
        self.last_evidence = {"source": "gemini_cloud", "model": self.model,
                              "image_sha256": hashlib.sha256(resized).hexdigest(),
                              "status": "requested"}
        try:
            result = self._client.interactions.create(**request)
        except Exception as err:
            # SDK exception strings can contain request URLs or bodies. Do not
            # copy those into logs or artifacts (especially API-key parameters).
            self.last_evidence.update(status="failed", error_type=type(err).__name__)
            log.warning("gemini call failed model=%s error_type=%s", self.model, type(err).__name__)
            raise GeminiError(f"Gemini request failed ({type(err).__name__}); no fallback used") from None
        latency_ms = (time.perf_counter() - started) * 1000
        usage_obj = getattr(result, "usage", None)
        usage = {key: getattr(usage_obj, key) for key in TOKEN_FIELDS
                 if getattr(usage_obj, key, None) is not None}
        status = getattr(result, "status", None)
        self.last_evidence.update(status=status, interaction_id=getattr(result, "id", None),
                                  latency_ms=latency_ms, usage=usage)
        log.info("gemini call model=%s latency_ms=%.0f status=%s usage=%s", self.model, latency_ms, status, usage)
        if status != "completed":
            raise GeminiError(f"Gemini interaction did not complete (status={status}); no fallback used")
        text = getattr(result, "output_text", None)
        if not isinstance(text, str) or not text.strip():
            raise GeminiError("Gemini returned no text; no fallback used")
        if json_schema is not None:
            try:
                json.loads(text)
            except json.JSONDecodeError:
                raise GeminiError("Gemini returned invalid JSON; no fallback used") from None
        return GemmaReply(text=text, latency_ms=latency_ms, usage=usage)

    def close(self) -> None:
        self._client.close()


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Optional one-frame Gemini cloud review; offline demo stays offline")
    parser.add_argument("image", type=Path)
    parser.add_argument("--allow-remote", action="store_true", help="Send this image to Google's Gemini API")
    parser.add_argument("--model", default=DEFAULT_MODEL)
    parser.add_argument("--prompt", default=(
        "Review this underwater simulator frame for visual quality. Describe coral realism, "
        "robot visibility, gripper contact, lighting and obvious artifacts. Distinguish visible "
        "evidence from uncertainty. Do not infer genetic compatibility or biological recovery from color."))
    parser.add_argument("--schema", type=Path, help="Optional JSON schema file")
    parser.add_argument("--out", type=Path, help="Save labelled model response and token usage")
    args = parser.parse_args(argv)
    if not args.allow_remote:
        parser.error("--allow-remote is required; images leave this computer only when explicitly enabled")
    logging.basicConfig(level=logging.INFO)
    client = None
    try:
        if args.image.stat().st_size > 8 * 1024 * 1024:
            raise ValueError("image file exceeds 8 MiB")
        image = args.image.read_bytes()
        schema = json.loads(args.schema.read_text()) if args.schema else None
        client = GeminiClient(allow_remote=True, model=args.model)
        reply = client.ask(args.prompt, image, schema)
        report = {**client.last_evidence, "text": reply.text}
        output = json.dumps(report, indent=2)
        if args.out:
            args.out.parent.mkdir(parents=True, exist_ok=True)
            args.out.write_text(output + "\n", encoding="utf-8")
        print(output)
        return 0
    except (GeminiError, ValueError, OSError) as err:
        parser.exit(1, f"Review failed: {err}\n")
    finally:
        if client is not None:
            client.close()


if __name__ == "__main__":
    raise SystemExit(main())
