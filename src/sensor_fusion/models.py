"""Sensor fusion domain models for S3M tactical tracking."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from enum import Enum
from math import sqrt
from typing import Any, Dict, List, Optional, Tuple


class SensorType(str, Enum):
    """Supported tactical sensor modalities for Layer 02 fusion."""

    EO_CAMERA = "EO_CAMERA"
    IR_CAMERA = "IR_CAMERA"
    LIDAR = "LIDAR"
    RADAR = "RADAR"
    ACOUSTIC = "ACOUSTIC"
    RF_SPECTRUM = "RF_SPECTRUM"
    GPS_INS = "GPS_INS"
    NETWORK = "NETWORK"

    @classmethod
    def from_value(cls, value: str | "SensorType") -> "SensorType":
        if isinstance(value, SensorType):
            return value
        if isinstance(value, str):
            normalized = value.strip().upper()
            if normalized in cls.__members__:
                return cls[normalized]
        raise ValueError(f"Invalid sensor type: {value}")


@dataclass
class SensorReading:
    """Single sensor report used for track association and fusion."""

    sensor_id: str
    sensor_type: SensorType
    timestamp: datetime
    data: Dict[str, Any]
    position: Optional[Tuple[float, float, float]] = None
    confidence: float = 1.0
    raw: Optional[bytes] = None

    def __post_init__(self) -> None:
        if not isinstance(self.sensor_id, str) or not self.sensor_id.strip():
            raise ValueError("sensor_id must be a non-empty string")
        self.sensor_type = SensorType.from_value(self.sensor_type)
        if not isinstance(self.timestamp, datetime):
            raise ValueError("timestamp must be datetime")
        if not isinstance(self.data, dict):
            raise ValueError("data must be a dictionary")
        if self.position is not None:
            if not isinstance(self.position, tuple) or len(self.position) != 3:
                raise ValueError("position must be a tuple of (x, y, z)")
            if not all(isinstance(v, (float, int)) for v in self.position):
                raise ValueError("position entries must be numeric")
            self.position = (float(self.position[0]), float(self.position[1]), float(self.position[2]))
        if not isinstance(self.confidence, (int, float)) or not (0.0 <= float(self.confidence) <= 1.0):
            raise ValueError("confidence must be in [0.0, 1.0]")
        self.confidence = float(self.confidence)
        if self.raw is not None and not isinstance(self.raw, (bytes, bytearray)):
            raise ValueError("raw must be bytes-like or None")

    def to_dict(self) -> Dict[str, Any]:
        payload = asdict(self)
        payload["sensor_type"] = self.sensor_type.value
        payload["timestamp"] = self.timestamp.isoformat()
        return payload

    def to_dict(self) -> Dict[str, Any]:
        """Serialize sensor reading for API responses and audit logs."""
        return {
            "sensor_id": self.sensor_id,
            "sensor_type": self.sensor_type.value,
            "timestamp": self.timestamp.isoformat(),
            "data": self.data,
            "position": self.position,
            "confidence": self.confidence,
        }


class TrackState(str, Enum):
    """Lifecycle state of a fused tactical track."""

    TENTATIVE = "TENTATIVE"
    CONFIRMED = "CONFIRMED"
    LOST = "LOST"
    DELETED = "DELETED"

    @classmethod
    def from_value(cls, value: str | "TrackState") -> "TrackState":
        if isinstance(value, TrackState):
            return value
        if isinstance(value, str):
            normalized = value.strip().upper()
            if normalized in cls.__members__:
                return cls[normalized]
        raise ValueError(f"Invalid track state: {value}")


@dataclass
class Track:
    """Fused multi-sensor object track used for tactical awareness."""

    track_id: str
    state: TrackState
    position: Tuple[float, float, float]
    velocity: Tuple[float, float, float]
    covariance: List[List[float]]
    last_update: datetime
    sensor_sources: List[str] = field(default_factory=list)
    classification: Optional[str] = None
    confidence: float = 0.5
    history: List[Dict[str, Any]] = field(default_factory=list)

    def __post_init__(self) -> None:
        if not isinstance(self.track_id, str) or not self.track_id.strip():
            raise ValueError("track_id must be a non-empty string")
        self.state = TrackState.from_value(self.state)
        if not (isinstance(self.position, tuple) and len(self.position) == 3):
            raise ValueError("position must be a tuple of (x, y, z)")
        if not (isinstance(self.velocity, tuple) and len(self.velocity) == 3):
            raise ValueError("velocity must be a tuple of (vx, vy, vz)")
        if not all(isinstance(v, (int, float)) for v in self.position + self.velocity):
            raise ValueError("position and velocity values must be numeric")
        self.position = (float(self.position[0]), float(self.position[1]), float(self.position[2]))
        self.velocity = (float(self.velocity[0]), float(self.velocity[1]), float(self.velocity[2]))
        if not isinstance(self.covariance, list):
            raise ValueError("covariance must be a list")
        if not isinstance(self.last_update, datetime):
            raise ValueError("last_update must be datetime")
        if not isinstance(self.sensor_sources, list) or any(not isinstance(s, str) for s in self.sensor_sources):
            raise ValueError("sensor_sources must be a list of strings")
        if not isinstance(self.confidence, (int, float)) or not (0.0 <= float(self.confidence) <= 1.0):
            raise ValueError("confidence must be in [0.0, 1.0]")
        self.confidence = float(self.confidence)
        if not isinstance(self.history, list):
            raise ValueError("history must be a list")

    def to_dict(self) -> Dict[str, Any]:
        payload = asdict(self)
        payload["state"] = self.state.value
        payload["last_update"] = self.last_update.isoformat()
        return payload

    def age_seconds(self) -> float:
        return max(0.0, (datetime.now(timezone.utc) - self.last_update).total_seconds())

    def distance_to(self, other_track: "Track") -> float:
        if not isinstance(other_track, Track):
            raise ValueError("other_track must be a Track")
        dx = self.position[0] - other_track.position[0]
        dy = self.position[1] - other_track.position[1]
        dz = self.position[2] - other_track.position[2]
        return sqrt(dx * dx + dy * dy + dz * dz)
