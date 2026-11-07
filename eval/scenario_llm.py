"""Test stand-in for Gemma on Moore Reef: real boxes from the render, labels as answers.

Keeps the rest of the pipeline honest. Depth projection, UV reading, genet
matching, planning and placement all run for real on what this returns.
"""

from __future__ import annotations

import json

import numpy as np

from eval.moore_reef import MooreReefRobot
from perception.gemma_client import GemmaReply
from perception.tests.fakes import cls_json


class ScenarioLLM:
    def __init__(self, robot: MooreReefRobot) -> None:
        self.robot = robot
        self.queue: list = []

    def ask(self, prompt, image_png, json_schema=None) -> GemmaReply:
        if '"objects"' in prompt:
            return GemmaReply(text=json.dumps({"objects": self._boxes()}), latency_ms=1.0)
        cluster = self.queue.pop(0)
        reply = cls_json(status=cluster.health_status, ctype=cluster.species_class, score=cluster.health_score)
        return GemmaReply(text=reply, latency_ms=1.0)

    def _boxes(self) -> list[dict]:
        view = self.robot.view()
        height, width = view.cluster_index.shape
        self.queue, boxes = [], []
        for index in np.unique(view.cluster_index):
            if index < 0:
                continue
            rows, cols = np.nonzero(view.cluster_index == index)
            if min(np.ptp(rows), np.ptp(cols)) < 24:
                continue  # a sliver at the frame edge
            self.queue.append(self.robot.reef.clusters[index])
            box = [rows.min() / height, cols.min() / width, (rows.max() + 1) / height, (cols.max() + 1) / width]
            boxes.append({"label": "coral", "box_2d": [round(v * 1000) for v in box]})
        return boxes
