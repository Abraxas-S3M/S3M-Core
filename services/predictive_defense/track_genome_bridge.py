"""Bridge between fused radar tracks and threat genome/prediction systems.

Military context:
Converts Layer 02 Track objects into genome-correlation features and
EntitySnapshot inputs for short-horizon prediction. This translation keeps
threat cues consistent across modules so defensive doctrine can prioritize
the most dangerous tracks first.
"""

from __future__ import annotations

import math
from datetime import datetime, timezone
from typing import Any, Dict, List

from src.prediction.prediction_models import EntitySnapshot, HistoricalObservation
from src.sensor_fusion.models import Track


class TrackGenomeBridge:
    """Convert fused tracks to prediction-ready entities with genome context."""

    _MAX_HISTORY_PER_TRACK = 50
    _MAX_OBSERVATIONS_FOR_SNAPSHOT = 10

    def __init__(self) -> None:
        self._track_history: Dict[str, List[Dict[str, Any]]] = {}

    def track_to_entity_snapshot(self, track: Track) -> EntitySnapshot:
        """Convert a fused Track into an EntitySnapshot for ShortHorizonPredictor."""
        self._validate_track(track)
        speed, heading = self._compute_speed_heading(track)

        history: List[HistoricalObservation] = []
        track_hist = self._track_history.get(track.track_id, [])
        for i, entry in enumerate(track_hist[-self._MAX_OBSERVATIONS_FOR_SNAPSHOT :]):
            history.append(
                HistoricalObservation(
                    timestamp_s=float(i),
                    position=entry["position"],
                    speed_mps=entry.get("speed", speed),
                    heading_deg=entry.get("heading", heading),
                    threat_level=entry.get("threat_level", "unknown"),
                )
            )

        # Tactical continuity: persist each new fused state for next forecast call.
        self._update_history(track, speed, heading)

        threat_level = self._classification_to_threat_level(track.classification or "")
        behavior_tags = self._derive_behavior_tags(track.classification, speed)

        return EntitySnapshot(
            entity_id=track.track_id,
            entity_type=track.classification or "unknown",
            position=track.position,
            speed_mps=speed,
            heading_deg=heading,
            threat_level=threat_level,
            behavior_tags=behavior_tags,
            confidence=track.confidence,
            volatility=self._compute_volatility(track.track_id),
            history=history,
        )

    def track_to_genome_features(self, track: Track) -> Dict[str, Any]:
        """Extract genome-correlation features from a track."""
        self._validate_track(track)
        speed, heading = self._compute_speed_heading(track)

        features: Dict[str, Any] = {
            "source_type": "sensor_fusion",
            "classification": track.classification or "unknown",
            "behavior_tags": [],
            "extracted_signature_features": {
                "approach_bearing_range": heading,
                "speed_range_mps": speed,
            },
            "raw_confidence": track.confidence,
        }
        if track.classification:
            lowered = track.classification.lower()
            features["behavior_tags"].append(lowered)
            if "uav" in lowered:
                features["behavior_tags"].extend(["drone", "uav"])
        return features

    def _update_history(self, track: Track, speed: float, heading: float) -> None:
        if track.track_id not in self._track_history:
            self._track_history[track.track_id] = []

        self._track_history[track.track_id].append(
            {
                "position": track.position,
                "speed": speed,
                "heading": heading,
                "threat_level": self._classification_to_threat_level(track.classification or ""),
                "timestamp": self._timestamp_for_history(track.last_update),
            }
        )

        if len(self._track_history[track.track_id]) > self._MAX_HISTORY_PER_TRACK:
            self._track_history[track.track_id] = self._track_history[track.track_id][
                -self._MAX_HISTORY_PER_TRACK :
            ]

    def _compute_volatility(self, track_id: str) -> float:
        hist = self._track_history.get(track_id, [])
        if len(hist) < 3:
            return 0.3
        headings = [float(h.get("heading", 0.0)) for h in hist[-self._MAX_OBSERVATIONS_FOR_SNAPSHOT :]]
        speeds = [float(h.get("speed", 0.0)) for h in hist[-self._MAX_OBSERVATIONS_FOR_SNAPSHOT :]]
        heading_var = self._variance(headings)
        speed_var = self._variance(speeds)
        return min(1.0, (heading_var / 180.0 + speed_var / 50.0) * 0.5)

    @staticmethod
    def _compute_speed_heading(track: Track) -> tuple[float, float]:
        vx, vy, vz = track.velocity
        speed = math.sqrt(vx * vx + vy * vy + vz * vz)
        heading = math.degrees(math.atan2(vx, vy)) % 360.0
        return speed, heading

    @staticmethod
    def _derive_behavior_tags(classification: str | None, speed: float) -> List[str]:
        behavior_tags: List[str] = []
        if classification:
            behavior_tags.append(classification.lower())
        if speed > 50:
            behavior_tags.append("high_speed")
        if speed < 10:
            behavior_tags.append("loitering")
        return behavior_tags

    @staticmethod
    def _validate_track(track: Track) -> None:
        if not isinstance(track, Track):
            raise ValueError("track must be a Track instance")
        if not isinstance(track.track_id, str) or not track.track_id.strip():
            raise ValueError("track.track_id must be a non-empty string")
        if not (isinstance(track.velocity, tuple) and len(track.velocity) == 3):
            raise ValueError("track.velocity must be a 3D tuple")
        if not (isinstance(track.position, tuple) and len(track.position) == 3):
            raise ValueError("track.position must be a 3D tuple")

    @staticmethod
    def _timestamp_for_history(last_update: datetime) -> str:
        if last_update.tzinfo is None:
            return last_update.replace(tzinfo=timezone.utc).isoformat()
        return last_update.astimezone(timezone.utc).isoformat()

    @staticmethod
    def _variance(values: List[float]) -> float:
        if not values:
            return 0.0
        mean = sum(values) / len(values)
        return sum((v - mean) ** 2 for v in values) / len(values)

    @staticmethod
    def _classification_to_threat_level(classification: str) -> str:
        c = classification.strip().upper()
        if "CRUISE_MISSILE" in c or "BALLISTIC" in c:
            return "critical"
        if "UAV" in c or "AIRCRAFT" in c or "HELICOPTER" in c:
            return "high"
        if c == "CLUTTER" or c == "UNKNOWN":
            return "low"
        return "medium"
