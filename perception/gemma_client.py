"""Thin client for a self-hosted Gemma behind an OpenAI-compatible endpoint
(vLLM `vllm serve`, see perception/modal_vllm.py). Deliberately NOT the Google
cloud Interactions API: the dive loop must not depend on Google's cloud.

Config (env vars, loaded from .env if present):
    GEMMA_BASE_URL   e.g. https://<workspace>--reef-gemma-serve.modal.run/v1
                     or http://localhost:8000/v1 for a vLLM on the sim box
    GEMMA_MODEL      served model name (default: gemma-4-31b-it)
    GEMMA_API_KEY    bearer token if the server was started with --api-key
    GEMMA_TIMEOUT_S  per-request timeout (default 60)
"""

from __future__ import annotations

import base64
import io
import logging
import os
import time
from dataclasses import dataclass, field
from typing import Any, Optional, Protocol

import numpy as np
import requests

log = logging.getLogger(__name__)


@dataclass
class GemmaReply:
    text: str
    latency_ms: float
    usage: dict[str, Any] = field(default_factory=dict)


class VisionLLM(Protocol):
    """Anything that can answer a prompt about one image. Tests use a fake."""

    def ask(self, prompt: str, image_png: bytes, json_schema: Optional[dict] = None) -> GemmaReply: ...


def encode_png(rgb: Any, max_side: int = 768) -> bytes:
    """HxWx3 uint8 array (or PIL image) -> PNG bytes, downscaled so the longest
    side is at most max_side (keeps request size and latency bounded)."""
    from PIL import Image

    img = rgb if isinstance(rgb, Image.Image) else Image.fromarray(np.asarray(rgb, dtype=np.uint8))
    img = img.convert("RGB")
    if max(img.size) > max_side:
        img.thumbnail((max_side, max_side))
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


class GemmaClient:
    def __init__(
        self,
        base_url: Optional[str] = None,
        model: Optional[str] = None,
        api_key: Optional[str] = None,
        timeout_s: Optional[float] = None,
    ) -> None:
        try:
            from dotenv import load_dotenv

            load_dotenv()
        except ImportError:
            pass
        self.base_url = (base_url or os.environ.get("GEMMA_BASE_URL", "")).rstrip("/")
        if not self.base_url:
            raise RuntimeError("GEMMA_BASE_URL is not set (see perception/gemma_client.py)")
        self.model = model or os.environ.get("GEMMA_MODEL", "gemma-4-31b-it")
        self.api_key = api_key or os.environ.get("GEMMA_API_KEY") or None
        self.timeout_s = timeout_s or float(os.environ.get("GEMMA_TIMEOUT_S", "60"))
        self._session = requests.Session()

    def ask(self, prompt: str, image_png: bytes, json_schema: Optional[dict] = None) -> GemmaReply:
        data_uri = "data:image/png;base64," + base64.b64encode(image_png).decode()
        body: dict[str, Any] = {
            "model": self.model,
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {"type": "image_url", "image_url": {"url": data_uri}},
                        {"type": "text", "text": prompt},
                    ],
                }
            ],
            "max_tokens": 1024,
            "temperature": 0.0,
        }
        if json_schema is not None:
            # vLLM structured outputs via the standard OpenAI response_format.
            body["response_format"] = {
                "type": "json_schema",
                "json_schema": {"name": "result", "schema": json_schema},
            }
        headers = {"Authorization": f"Bearer {self.api_key}"} if self.api_key else {}
        t0 = time.perf_counter()
        r = self._session.post(
            f"{self.base_url}/chat/completions", json=body, headers=headers, timeout=self.timeout_s
        )
        latency_ms = (time.perf_counter() - t0) * 1000
        r.raise_for_status()
        payload = r.json()
        text = payload["choices"][0]["message"]["content"] or ""
        usage = payload.get("usage") or {}
        log.info("gemma call model=%s latency_ms=%.0f usage=%s", self.model, latency_ms, usage)
        return GemmaReply(text=text, latency_ms=latency_ms, usage=usage)
