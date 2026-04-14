"""Bridge fused radar tracks into genome correlation and trajectory snapshots.

Military context:
The bridge standardizes radar-fused kinematics into explainable behavior
features so genome correlation and predictive forecasting operate on the same
tactical picture.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
import math
from threading import RLock
from typing import Any, Dict, List, Optional, Tuple

from src.fusion.threat_genome_correlator import GenomeObservation
from src.prediction.prediction_models import EntitySnapshot, HistoricalObservation


def _safe_now() -> datetime:
    return datetime.now(timezone.utc)


def _as_vec3(raw: Any) -> Tuple[float, float, float]:
    if isinstance(raw, tuple) and len(raw) == 3:
        return (float(raw[0]), float(raw[1]), float(raw[2]))
    if isinstance(raw, list) and len(raw) == 3:
        return (float(raw[0]), float(raw[1]), float(raw[2]))
    return (0.0, 0.0, 0.0)


def _bearing_from_velocity(velocity_mps: Tuple[float, float, float]) -> float:
    vx, vy, _ = velocity_mps
    if abs(vx) < 1e-6 and abs(vy) < 1e-6:
        return 0.0
    return math.degrees(math.atan2(vy, vx)) % 360.0


def _speed_from_velocity(velocity_mps: Tuple[float, float, float]) -> float:
    vx, vy, vz = velocity_mps
    return math.sqrt(vx * vx + vy * vy + vz * vz)


def _entity_type_from_classification(classification: str) -> str:
    cls = classification.lower()
    if "uav" in cls or "drone" in cls:
        return "uav"
    if "missile" in cls:
        return "missile"
    if "helicopter" in cls:
        return "helicopter"
    if "aircraft" in cls or "fighter" in cls:
        return "aircraft"
    return "unknown"


@dataclass
class TrackGenomeContext:
    """Unified output for genome correlation and trajectory prediction."""

    track_id: str
    genome_observation: GenomeObservation
    entity_snapshot: EntitySnapshot
    behavior_context: Dict[str, Any] = field(default_factory=dict)


class TrackGenomeBridge:
    """Convert heterogeneous track objects into predictive-defense inputs."""

    def __init__(self, history_limit: int = 20) -> None:
        self._history_limit = max(3, int(history_limit))
        self._history_by_track: Dict[str, List[HistoricalObservation]] = {}
        self._lock = RLock()

    def to_context(self, track: Any) -> TrackGenomeContext:
        """Build a combined genome/prediction context from one fused track."""
        track_id = str(getattr(track, "track_id", "")).strip()
        if not track_id:
            raise ValueError("track_id is required on incoming track")

        last_update = getattr(track, "last_update", None)
        if not isinstance(last_update, datetime):
            last_update = _safe_now()
        elif last_update.tzinfo is None:
            last_update = last_update.replace(tzinfo=timezone.utc)
        else:
            last_update = last_update.astimezone(timezone.utc)

        position = _as_vec3(getattr(track, "position", (0.0, 0.0, 0.0)))
        velocity = _as_vec3(getattr(track, "velocity", (0.0, 0.0, 0.0)))
        speed_mps = _speed_from_velocity(velocity)
        heading_deg = _bearing_from_velocity(velocity)

        metadata = getattr(track, "metadata", {}) or {}
        classification = str(getattr(track, "classification", metadata.get("classification", "unknown")) or "unknown")
        confidence = float(getattr(track, "confidence", metadata.get("confidence", 0.5)) or 0.5)
        confidence = max(0.0, min(1.0, confidence))
        threat_level = str(metadata.get("threat_level", "guarded") or "guarded")
        regions = self._extract_regions(metadata)
        behavior_tags = self._extract_behavior_tags(
            speed_mps=speed_mps,
            heading_deg=heading_deg,
            position_m=position,
            classification=classification,
            metadata=metadata,
        )

        snapshot = self._build_entity_snapshot(
            track_id=track_id,
            last_update=last_update,
            position=position,
            speed_mps=speed_mps,
            heading_deg=heading_deg,
            classification=classification,
            confidence=confidence,
            behavior_tags=behavior_tags,
            threat_level=threat_level,
        )
        behavior_context = self._build_behavior_context(
            position=position,
            speed_mps=speed_mps,
            heading_deg=heading_deg,
            behavior_tags=behavior_tags,
            metadata=metadata,
        )
        genome_observation = GenomeObservation(
            observation_id=f"obs-{track_id}-{int(last_update.timestamp())}",
            source_type="radar_fusion",
            source_id=track_id,
            timestamp=last_update,
            extracted_signature_features={
                "movement": {
                    "speed_mps": speed_mps,
                    "heading_deg": heading_deg,
                    "altitude_m": position[2],
                    "bearing_bucket_deg": round(heading_deg / 10.0) * 10.0,
                },
                "temporal": {
                    "hour_utc": last_update.hour,
                },
                "speed_mps": speed_mps,
                "heading_deg": heading_deg,
                "altitude_m": position[2],
            },
            behavior_tags=behavior_tags,
            raw_confidence=confidence,
            classification=classification,
            threat_level=threat_level,
            regions=regions,
        )
        return TrackGenomeContext(
            track_id=track_id,
            genome_observation=genome_observation,
            entity_snapshot=snapshot,
            behavior_context=behavior_context,
        )

    def to_contexts(self, tracks: List[Any]) -> List[TrackGenomeContext]:
        contexts: List[TrackGenomeContext] = []
        for track in tracks:
            try:
                contexts.append(self.to_context(track))
            except ValueError:
                # Tactical continuity: skip malformed tracks without halting cycle.
                continue
        return contexts

    def _build_entity_snapshot(
        self,
        *,
        track_id: str,
        last_update: datetime,
        position: Tuple[float, float, float],
        speed_mps: float,
        heading_deg: float,
        classification: str,
        confidence: float,
        behavior_tags: List[str],
        threat_level: str,
    ) -> EntitySnapshot:
        with self._lock:
            history = self._history_by_track.setdefault(track_id, [])
            history.append(
                HistoricalObservation(
                    timestamp_s=last_update.timestamp(),
                    position=position,
                    speed_mps=speed_mps,
                    heading_deg=heading_deg,
                    threat_level=threat_level,
                )
            )
            if len(history) > self._history_limit:
                history[:] = history[-self._history_limit :]
            rolling_history = list(history)

        return EntitySnapshot(
            entity_id=track_id,
            entity_type=_entity_type_from_classification(classification),
            position=position,
            speed_mps=speed_mps,
            heading_deg=heading_deg,
            threat_level=threat_level,
            behavior_tags=behavior_tags,
            confidence=confidence,
            volatility=self._estimate_volatility(rolling_history),
            history=rolling_history,
        )

    @staticmethod
    def _estimate_volatility(history: List[HistoricalObservation]) -> float:
        if len(history) < 2:
            return 0.0
        speeds = [point.speed_mps for point in history]
        headings = [point.heading_deg for point in history]
        avg_speed = sum(speeds) / len(speeds)
        speed_var = sum((s - avg_speed) ** 2 for s in speeds) / len(speeds)
        heading_jitter = 0.0
        for idx in range(1, len(headings)):
            diff = abs(headings[idx] - headings[idx - 1])
            heading_jitter += min(diff, 360.0 - diff)
        heading_jitter = heading_jitter / max(1, len(headings) - 1)
        return max(0.0, min(1.0, (math.sqrt(speed_var) / 20.0) + (heading_jitter / 180.0)))

    @staticmethod
    def _extract_regions(metadata: Dict[str, Any]) -> List[str]:
        raw_regions = metadata.get("regions", metadata.get("region", []))
        if isinstance(raw_regions, str) and raw_regions.strip():
            return [raw_regions.strip()]
        if isinstance(raw_regions, list):
            return [str(value) for value in raw_regions if str(value).strip()]
        return []

    @staticmethod
    def _extract_behavior_tags(
        *,
        speed_mps: float,
        heading_deg: float,
        position_m: Tuple[float, float, float],
        classification: str,
        metadata: Dict[str, Any],
    ) -> List[str]:
        tags = {str(tag).lower() for tag in metadata.get("behavior_tags", [])}
        if speed_mps > 35.0:
            tags.add("high_speed")
        if speed_mps < 8.0:
            tags.add("loiter")
        if position_m[2] < 250.0:
            tags.add("low_altitude")
        if 170.0 <= heading_deg <= 190.0:
            tags.add("southern_approach")
        if "uav" in classification.lower() or "drone" in classification.lower():
            tags.add("uav")
        return sorted(tags)

    @staticmethod
    def _build_behavior_context(
        *,
        position: Tuple[float, float, float],
        speed_mps: float,
        heading_deg: float,
        behavior_tags: List[str],
        metadata: Dict[str, Any],
    ) -> Dict[str, Any]:
        radial_distance_m = math.sqrt(position[0] ** 2 + position[1] ** 2)
        return {
            "speed_mps": speed_mps,
            "heading_deg": heading_deg,
            "radial_distance_m": radial_distance_m,
            "altitude_m": position[2],
            "behavior_tags": list(behavior_tags),
            "sensor_sources": list(metadata.get("sensor_sources", [])),
        }
