"""Bridge fused tracks into predictor-ready entity snapshots.

Military context:
This bridge translates radar-fusion track state into deterministic prediction
input so doctrine logic can run fully offline during contested operations.
"""

from __future__ import annotations

from math import atan2, degrees, sqrt
from typing import Any, Dict, List, Tuple

from src.prediction.prediction_models import EntitySnapshot, HistoricalObservation
from src.sensor_fusion.models import Track


def _to_xyz(raw_position: Any) -> Tuple[float, float, float]:
    if not isinstance(raw_position, (tuple, list)) or len(raw_position) != 3:
        raise ValueError("position must contain exactly 3 numeric values")
    return (float(raw_position[0]), float(raw_position[1]), float(raw_position[2]))


class TrackGenomeBridge:
    """Converts sensor-fusion tracks to prediction-model snapshots."""

    def track_to_entity_snapshot(self, track: Track) -> EntitySnapshot:
        if not isinstance(track, Track):
            raise ValueError("track must be a Track instance")

        speed_mps = sqrt(
            (track.velocity[0] * track.velocity[0])
            + (track.velocity[1] * track.velocity[1])
            + (track.velocity[2] * track.velocity[2])
        )
        heading_deg = (degrees(atan2(track.velocity[1], track.velocity[0])) + 360.0) % 360.0
        threat_level = self._classification_to_threat(track.classification)
        history = self._build_history(track.history, fallback_position=track.position, fallback_speed=speed_mps)
        behavior_tags = self._build_behavior_tags(track.classification, speed_mps)

        return EntitySnapshot(
            entity_id=track.track_id,
            entity_type=self._classification_to_entity_type(track.classification),
            position=track.position,
            speed_mps=speed_mps,
            heading_deg=heading_deg,
            threat_level=threat_level,
            behavior_tags=behavior_tags,
            confidence=track.confidence,
            volatility=self._estimate_volatility(history, speed_mps=speed_mps),
            history=history,
        )

    def _build_history(
        self,
        history: List[Dict[str, Any]],
        *,
        fallback_position: Tuple[float, float, float],
        fallback_speed: float,
    ) -> List[HistoricalObservation]:
        out: List[HistoricalObservation] = []
        for idx, entry in enumerate(history[-10:]):
            if not isinstance(entry, dict):
                continue
            position_raw = entry.get("position", fallback_position)
            velocity_raw = entry.get("velocity", (fallback_speed, 0.0, 0.0))
            try:
                position = _to_xyz(position_raw)
                velocity = _to_xyz(velocity_raw)
            except (TypeError, ValueError):
                continue
            speed = sqrt((velocity[0] * velocity[0]) + (velocity[1] * velocity[1]) + (velocity[2] * velocity[2]))
            heading = (degrees(atan2(velocity[1], velocity[0])) + 360.0) % 360.0
            threat_level = self._classification_to_threat(entry.get("classification"))
            out.append(
                HistoricalObservation(
                    timestamp_s=float(idx),
                    position=position,
                    speed_mps=speed,
                    heading_deg=heading,
                    threat_level=threat_level,
                )
            )
        return out

    def _estimate_volatility(self, history: List[HistoricalObservation], *, speed_mps: float) -> float:
        if len(history) < 2:
            return min(1.0, max(0.0, speed_mps / 120.0))
        speed_changes = [abs(history[idx].speed_mps - history[idx - 1].speed_mps) for idx in range(1, len(history))]
        heading_changes = [
            min(
                abs(history[idx].heading_deg - history[idx - 1].heading_deg),
                360.0 - abs(history[idx].heading_deg - history[idx - 1].heading_deg),
            )
            for idx in range(1, len(history))
        ]
        avg_speed_delta = sum(speed_changes) / max(1, len(speed_changes))
        avg_heading_delta = sum(heading_changes) / max(1, len(heading_changes))
        return min(1.0, (avg_speed_delta / 40.0) + (avg_heading_delta / 180.0))

    def _build_behavior_tags(self, classification: Any, speed_mps: float) -> List[str]:
        tags: List[str] = []
        classification_text = str(classification or "unknown").lower()
        if "uav" in classification_text:
            tags.append("uav")
        if "missile" in classification_text:
            tags.append("missile")
        if speed_mps >= 70.0:
            tags.append("high_speed")
        return tags

    def _classification_to_entity_type(self, classification: Any) -> str:
        text = str(classification or "unknown").strip().lower()
        if "uav" in text:
            return "uav"
        if "missile" in text:
            return "missile"
        if "aircraft" in text:
            return "aircraft"
        return "unknown"

    def _classification_to_threat(self, classification: Any) -> str:
        text = str(classification or "unknown").strip().upper()
        if "CRUISE_MISSILE" in text:
            return "critical"
        if "ENEMY" in text or "HOSTILE" in text:
            return "high"
        if "UNKNOWN" not in text and text:
            return "guarded"
        return "unknown"
