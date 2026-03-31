"""Sensor registration and tactical fusion pipeline manager."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple
from uuid import uuid4

from src.sensor_fusion.models import SensorReading, SensorType, Track, TrackState
from src.sensor_fusion.track_fuser import TrackFuser
from src.threat_detection.models import ThreatCategory, ThreatEvent, ThreatLevel, ThreatSource


class SensorManager:
    """Register sensors, ingest readings, and produce fused tactical tracks."""

    def __init__(self) -> None:
        self._sensors: Dict[str, Dict[str, Any]] = {}
        self._pending_readings: List[SensorReading] = []
        self._fuser = TrackFuser()

    def register_sensor(self, sensor_id: str, sensor_type: SensorType | str, config: Optional[Dict[str, Any]] = None) -> None:
        if not isinstance(sensor_id, str) or not sensor_id.strip():
            raise ValueError("sensor_id must be a non-empty string")
        sensor_enum = SensorType.from_value(sensor_type)
        if config is not None and not isinstance(config, dict):
            raise ValueError("config must be a dictionary or None")
        self._sensors[sensor_id] = {
            "sensor_id": sensor_id,
            "sensor_type": sensor_enum,
            "config": config or {},
            "registered_at": datetime.now(timezone.utc),
        }

    def ingest(
        self,
        sensor_id: str,
        data: Dict[str, Any],
        position: Optional[Tuple[float, float, float]] = None,
        confidence: float = 1.0,
    ) -> SensorReading:
        if sensor_id not in self._sensors:
            raise ValueError(f"Sensor '{sensor_id}' is not registered")
        if not isinstance(data, dict):
            raise ValueError("data must be a dictionary")
        if not isinstance(confidence, (int, float)) or not (0.0 <= float(confidence) <= 1.0):
            raise ValueError("confidence must be between 0.0 and 1.0")
        if position is None:
            if not all(axis in data for axis in ("x", "y", "z")):
                raise ValueError("position is required or data must include numeric x/y/z fields")
            position = (float(data["x"]), float(data["y"]), float(data["z"]))

        sensor_info = self._sensors[sensor_id]
        reading = SensorReading(
            sensor_id=sensor_id,
            sensor_type=sensor_info["sensor_type"],
            timestamp=datetime.now(timezone.utc),
            data=data,
            position=position,
            confidence=float(confidence),
        )
        self._pending_readings.append(reading)
        return reading

    def process(self) -> List[Track]:
        if not self._pending_readings:
            return self._fuser.get_tracks()
        readings = list(self._pending_readings)
        self._pending_readings.clear()
        return self._fuser.update(readings)

    def get_sensors(self) -> List[Dict[str, Any]]:
        output: List[Dict[str, Any]] = []
        for sensor in self._sensors.values():
            output.append(
                {
                    "sensor_id": sensor["sensor_id"],
                    "sensor_type": sensor["sensor_type"].value,
                    "config": sensor["config"],
                    "registered_at": sensor["registered_at"].isoformat(),
                }
            )
        return output

    def get_fused_tracks(self) -> List[Track]:
        return self._fuser.get_tracks()

    def _classification_to_level(self, classification: str) -> ThreatLevel:
        lowered = classification.lower()
        if any(token in lowered for token in ["aircraft", "jet", "missile"]):
            return ThreatLevel.CRITICAL
        if any(token in lowered for token in ["tank", "warship", "helicopter"]):
            return ThreatLevel.HIGH
        if "soldier" in lowered:
            return ThreatLevel.MEDIUM
        return ThreatLevel.LOW

    def _classification_to_category(self, classification: str) -> ThreatCategory:
        lowered = classification.lower()
        if any(token in lowered for token in ["soldier", "personnel", "observer"]):
            return ThreatCategory.SURVEILLANCE
        if any(token in lowered for token in ["jammer", "rf", "ew"]):
            return ThreatCategory.ELECTRONIC_WARFARE
        if classification:
            return ThreatCategory.KINETIC
        return ThreatCategory.UNKNOWN

    def to_threat_events(self) -> List[ThreatEvent]:
        events: List[ThreatEvent] = []
        for track in self._fuser.get_tracks(state=TrackState.CONFIRMED):
            if not track.classification:
                continue
            level = self._classification_to_level(track.classification)
            category = self._classification_to_category(track.classification)
            event = ThreatEvent(
                event_id=str(uuid4()),
                source=ThreatSource.SENSOR_FUSION,
                level=level,
                category=category,
                title=f"Fused track {track.track_id} ({track.classification})",
                description=(
                    "Multi-sensor fusion confirmed a tactical track. "
                    "Use this event to prioritize force-protection actions."
                ),
                raw_data=track.to_dict(),
                confidence=track.confidence,
                location={"x": track.position[0], "y": track.position[1], "z": track.position[2]},
                asset_ids=list(track.sensor_sources),
                recommended_action="Task ISR assets to maintain continuous contact and verify intent.",
            )
            events.append(event)
        return events

    def health_check(self) -> Dict[str, Any]:
        return {
            "registered_sensors": len(self._sensors),
            "pending_readings": len(self._pending_readings),
            "track_stats": self._fuser.get_stats(),
        }
