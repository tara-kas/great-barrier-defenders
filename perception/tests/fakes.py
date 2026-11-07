"""Canned-response stand-in for GemmaClient: no network, records calls."""

from __future__ import annotations

import json
from typing import Callable, Optional, Union

import numpy as np

from agent.robot_interface import RGBDFrame
from perception.gemma_client import GemmaReply

Responder = Callable[[str, bytes], str]


class FakeLLM:
    def __init__(self, responses: Union[list[str], Responder]) -> None:
        self._responses = responses
        self.calls: list[str] = []

    def ask(self, prompt: str, image_png: bytes, json_schema: Optional[dict] = None) -> GemmaReply:
        self.calls.append(prompt)
        if callable(self._responses):
            text = self._responses(prompt, image_png)
        else:
            text = self._responses.pop(0)
        return GemmaReply(text=text, latency_ms=12.0)


def cls_json(status="LIVE", ctype="acropora_branching", score=0.9, conf=0.9, is_coral=True) -> str:
    return json.dumps(
        {"evidence": "test", "is_coral": is_coral, "coral_type": ctype,
         "health_status": status, "health_score": score, "confidence": conf}
    )


def flat_frame(w=200, h=100, depth=2.0, f=100.0) -> RGBDFrame:
    """Camera looking straight down from 2 m: robot +z up, camera +z down."""
    cam_to_robot = np.array(
        [[1, 0, 0, 0], [0, -1, 0, 0], [0, 0, -1, 0], [0, 0, 0, 1]], dtype=float
    )  # 180 deg about x: optical axis points along robot -z
    return RGBDFrame(
        rgb=np.full((h, w, 3), 120, dtype=np.uint8),
        depth=np.full((h, w), depth, dtype=float),
        intrinsics=(f, f, w / 2, h / 2),
        camera_to_robot=cam_to_robot,
    )
