"""Survey step: one RGBD frame + robot pose -> SemanticSeabedRegistry updates.

    detect (Gemma boxes) -> crop -> classify (Gemma) -> project (depth) -> associate -> upsert

Every observation comes back with an evidence dict so the FSM can log *why*
an entry was created, updated, or skipped (CLAUDE.md section 8). Low-confidence
or non-coral results are abstained on, never written to the registry.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from typing import Any, Literal, Optional

import numpy as np
import requests

from agent.robot_interface import Pose, RGBDFrame
from perception.classify import ClassificationError, ClassificationResult, classify_crop, crop_box
from perception.detect import Detection, DetectionError, detect_corals
from perception.gemma_client import VisionLLM
from perception.projection import BoxProjection, project_box
from perception.registry import SemanticMapEntry, SemanticSeabedRegistry

log = logging.getLogger(__name__)

Action = Literal["new", "updated", "kept", "abstained", "error"]


@dataclass
class Observation:
    detection: Detection
    action: Action
    reason: str
    cluster_id: Optional[str] = None
    classification: Optional[ClassificationResult] = None
    projection: Optional[BoxProjection] = None

    def evidence(self) -> dict[str, Any]:
        ev: dict[str, Any] = {
            "box_xyxy": list(self.detection.box_xyxy),
            "detector_label": self.detection.label,
            "action": self.action,
            "reason": self.reason,
            "cluster_id": self.cluster_id,
        }
        if self.classification:
            ev["classification"] = self.classification.to_evidence()
        if self.projection:
            ev["position_world"] = list(self.projection.position_world)
            ev["median_depth_m"] = self.projection.median_depth
            ev["depth_valid_fraction"] = self.projection.valid_fraction
        return ev


@dataclass
class SurveyResult:
    observations: list[Observation] = field(default_factory=list)
    detect_latency_ms: float = 0.0
    error: Optional[str] = None

    def evidence(self) -> dict[str, Any]:
        return {
            "detect_latency_ms": self.detect_latency_ms,
            "error": self.error,
            "observations": [o.evidence() for o in self.observations],
        }


class Surveyor:
    def __init__(
        self,
        llm: VisionLLM,
        registry: SemanticSeabedRegistry,
        min_confidence: float = 0.6,
        merge_radius_m: float = 0.4,
        min_depth_valid_fraction: float = 0.2,
    ) -> None:
        self.llm = llm
        self.registry = registry
        self.min_confidence = min_confidence
        self.merge_radius_m = merge_radius_m
        self.min_depth_valid_fraction = min_depth_valid_fraction
        # Confidence of the classification currently stored per cluster, so a
        # blurrier later view does not overwrite a clearer earlier one.
        self._confidence: dict[str, float] = {}

    def _next_cluster_id(self) -> str:
        nums = [int(m.group(1)) for e in self.registry.all() if (m := re.fullmatch(r"cluster_(\d+)", e.cluster_id))]
        return f"cluster_{(max(nums) + 1) if nums else 1:03d}"

    def _nearest(self, pos: tuple[float, float, float]) -> Optional[SemanticMapEntry]:
        best, best_d = None, self.merge_radius_m
        for e in self.registry.all():
            d = float(np.linalg.norm(np.subtract(e.position_world, pos)))
            if d <= best_d:
                best, best_d = e, d
        return best

    def observe(self, det: Detection, frame: RGBDFrame, pose: Pose) -> Observation:
        try:
            proj = project_box(frame, pose, det.box_xyxy)
        except ValueError as e:
            return Observation(det, "abstained", f"no usable depth: {e}")
        if proj.valid_fraction < self.min_depth_valid_fraction:
            return Observation(det, "abstained", f"depth valid on only {proj.valid_fraction:.0%} of box", projection=proj)

        try:
            cls = classify_crop(self.llm, crop_box(frame.rgb, det.box_xyxy))
        except ClassificationError as e:
            return Observation(det, "abstained", f"unparseable classification: {e}", projection=proj)
        except requests.RequestException as e:
            return Observation(det, "abstained", f"classifier unreachable: {e}", projection=proj)

        if not cls.is_coral:
            return Observation(det, "abstained", "classifier says not coral", classification=cls, projection=proj)
        if cls.confidence < self.min_confidence:
            return Observation(
                det, "abstained", f"confidence {cls.confidence:.2f} < {self.min_confidence:.2f}",
                classification=cls, projection=proj,
            )

        existing = self._nearest(proj.position_world)
        if existing is not None:
            if existing.sampled_or_restored or existing.health_status == "RESTORED":
                return Observation(
                    det, "kept", "matches an entry the mission already acted on",
                    cluster_id=existing.cluster_id, classification=cls, projection=proj,
                )
            if cls.confidence < self._confidence.get(existing.cluster_id, 0.0):
                return Observation(
                    det, "kept", "earlier view of this cluster was more confident",
                    cluster_id=existing.cluster_id, classification=cls, projection=proj,
                )
            cid, action, reason = existing.cluster_id, "updated", "re-observed within merge radius"
        else:
            cid, action, reason = self._next_cluster_id(), "new", "no existing cluster within merge radius"

        self.registry.upsert(
            SemanticMapEntry(
                cluster_id=cid,
                species_class=cls.species_class,
                health_status=cls.health_status,
                health_score=cls.health_score,
                position_world=proj.position_world,
                bounding_box_extent=proj.bounding_box_extent,
                optimal_graft_pose_world=existing.optimal_graft_pose_world if existing else None,
            )
        )
        self._confidence[cid] = cls.confidence
        return Observation(det, action, reason, cluster_id=cid, classification=cls, projection=proj)  # type: ignore[arg-type]

    def survey_frame(self, frame: RGBDFrame, pose: Pose) -> SurveyResult:
        try:
            dets, latency = detect_corals(self.llm, frame.rgb)
        except (DetectionError, ValueError, requests.RequestException) as e:
            log.warning("detection failed: %s", e)
            return SurveyResult(error=f"detection failed: {e}")
        result = SurveyResult(detect_latency_ms=latency)
        for det in dets:
            obs = self.observe(det, frame, pose)
            log.info("survey %s %s: %s", obs.action, obs.cluster_id, obs.reason)
            result.observations.append(obs)
        return result
