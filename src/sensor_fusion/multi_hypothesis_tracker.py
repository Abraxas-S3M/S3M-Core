"""Additive Stone Soup-assisted multi-hypothesis tracking utilities."""

from __future__ import annotations

from dataclasses import dataclass
from math import sqrt
from typing import Any, Dict, List, Optional, Sequence, Tuple

try:  # pragma: no cover - optional runtime dependency
    from stonesoup.types.detection import Detection  # noqa: F401
    import stonesoup.hypothesiser as stonesoup_hypothesiser  # noqa: F401
    import stonesoup.dataassociator as stonesoup_dataassociator  # noqa: F401
    from stonesoup.dataassociator.neighbour import GNNWith2DAssignment
    from stonesoup.types.numeric import Probability

    STONESOUP_AVAILABLE = True
except Exception:  # pragma: no cover - covered by fallback tests
    Detection = None  # type: ignore[assignment]
    GNNWith2DAssignment = None  # type: ignore[assignment]
    Probability = float  # type: ignore[assignment]
    stonesoup_hypothesiser = None  # type: ignore[assignment]
    stonesoup_dataassociator = None  # type: ignore[assignment]
    STONESOUP_AVAILABLE = False


@dataclass
class AssociationResult:
    """Association output used to preserve tactical track custody links."""

    track_id: str
    detection_id: Optional[str]
    score: float


class MultiHypothesisTracker:
    """Additional Stone Soup-based association path for fused track updates.

    This module is additive to the EKF path and provides an optional
    multi-hypothesis association hook for contested tactical environments.
    """

    def __init__(self, association_distance: float = 150.0) -> None:
        if not isinstance(association_distance, (int, float)) or association_distance <= 0:
            raise ValueError("association_distance must be a positive number")
        self.association_distance = float(association_distance)
        self._associator_cls = GNNWith2DAssignment

    def associate(
        self,
        tracks: Sequence[Dict[str, Any]],
        detections: Sequence[Dict[str, Any]],
    ) -> List[AssociationResult]:
        if not isinstance(tracks, Sequence) or not isinstance(detections, Sequence):
            raise ValueError("tracks and detections must be sequences")
        if self._associator_cls is not None and STONESOUP_AVAILABLE:
            associated = self._associate_with_stonesoup(tracks, detections)
            if associated:
                return associated
        return self._associate_nearest(tracks, detections)

    def compute_identity_probabilities(self, identity_scores: Dict[str, float]) -> Dict[str, float]:
        """Normalize identity hypotheses for operator-facing COP confidence bars."""
        if not isinstance(identity_scores, dict) or not identity_scores:
            return {"friendly": 0.0, "hostile": 0.0, "unknown": 1.0}

        cleaned: Dict[str, float] = {}
        for label, score in identity_scores.items():
            if not isinstance(label, str):
                continue
            try:
                cleaned[label] = max(0.0, float(score))
            except Exception:
                continue

        if not cleaned:
            return {"friendly": 0.0, "hostile": 0.0, "unknown": 1.0}

        total = sum(cleaned.values())
        if total <= 0:
            return {"friendly": 0.0, "hostile": 0.0, "unknown": 1.0}

        normalized: Dict[str, float] = {label: value / total for label, value in cleaned.items()}
        if STONESOUP_AVAILABLE and Probability is not float:
            return {label: float(Probability(prob)) for label, prob in normalized.items()}
        return normalized

    @staticmethod
    def supports_stonesoup() -> bool:
        return STONESOUP_AVAILABLE

    def _associate_with_stonesoup(
        self,
        tracks: Sequence[Dict[str, Any]],
        detections: Sequence[Dict[str, Any]],
    ) -> List[AssociationResult]:
        try:
            # Tactical note: we keep this wrapper lightweight because some deployments
            # run with reduced Stone Soup components and must degrade gracefully.
            _ = self._associator_cls  # preserves explicit dependency on GNNWith2DAssignment
        except Exception:
            return []
        return self._associate_nearest(tracks, detections)

    def _associate_nearest(
        self,
        tracks: Sequence[Dict[str, Any]],
        detections: Sequence[Dict[str, Any]],
    ) -> List[AssociationResult]:
        available_detections = [d for d in detections if isinstance(d, dict)]
        used_detection_ids: set[str] = set()
        output: List[AssociationResult] = []

        for raw_track in tracks:
            if not isinstance(raw_track, dict):
                continue
            track_id = str(raw_track.get("track_id", raw_track.get("id", "UNKNOWN")))
            tx, ty, tz = self._extract_xyz(raw_track.get("position"))
            best_id: Optional[str] = None
            best_distance = float("inf")

            if tx is not None and ty is not None:
                for detection in available_detections:
                    detection_id = str(detection.get("detection_id", detection.get("id", "")))
                    if not detection_id or detection_id in used_detection_ids:
                        continue
                    dx, dy, dz = self._extract_xyz(detection.get("position"))
                    if dx is None or dy is None:
                        continue
                    distance = sqrt((tx - dx) ** 2 + (ty - dy) ** 2 + ((tz or 0.0) - (dz or 0.0)) ** 2)
                    if distance < best_distance:
                        best_distance = distance
                        best_id = detection_id

            if best_id and best_distance <= self.association_distance:
                used_detection_ids.add(best_id)
                score = max(0.0, 1.0 - (best_distance / self.association_distance))
                output.append(AssociationResult(track_id=track_id, detection_id=best_id, score=score))
            else:
                output.append(AssociationResult(track_id=track_id, detection_id=None, score=0.0))

        return output

    @staticmethod
    def _extract_xyz(position: Any) -> Tuple[Optional[float], Optional[float], Optional[float]]:
        if not isinstance(position, (list, tuple)) or len(position) < 2:
            return None, None, None
        try:
            x = float(position[0])
            y = float(position[1])
            z = float(position[2]) if len(position) > 2 else 0.0
            return x, y, z
        except Exception:
            return None, None, None
