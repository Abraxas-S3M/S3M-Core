"""Data models for S3M Layer 09 sensor and remote sensing analytics.

These models define wide-area maritime and border surveillance entities used to
bridge satellite/remote sensors into tactical Phase 5 fusion workflows.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple
from uuid import uuid4


def _iso(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).isoformat()


@dataclass
class SARImageMeta:
    image_id: str
    source: str
    filepath: str
    width: int
    height: int
    acquisition_time: datetime
    polarization: str
    resolution_meters: float
    center_lat: float
    center_lon: float
    bounds: Dict[str, float]
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        payload = asdict(self)
        payload["acquisition_time"] = _iso(self.acquisition_time)
        return payload


@dataclass
class SARDetection:
    detection_id: str
    image_id: str
    bbox: Tuple[float, float, float, float]
    geo_position: Tuple[float, float]
    confidence: float
    class_name: str
    estimated_length_meters: float
    estimated_width_meters: float
    heading_deg: Optional[float]
    speed_knots: Optional[float]
    model_used: str
    timestamp: datetime

    def to_dict(self) -> Dict[str, Any]:
        payload = asdict(self)
        payload["timestamp"] = _iso(self.timestamp)
        payload["model_not_loaded"] = self.model_used.lower().startswith("stub")
        return payload

    def area_sq_meters(self) -> float:
        return max(0.0, float(self.estimated_length_meters) * float(self.estimated_width_meters))


class VesselClassification(str, Enum):
    CARGO = "CARGO"
    TANKER = "TANKER"
    FISHING = "FISHING"
    MILITARY_SURFACE = "MILITARY_SURFACE"
    MILITARY_SUBMARINE = "MILITARY_SUBMARINE"
    PATROL = "PATROL"
    TUG = "TUG"
    PASSENGER = "PASSENGER"
    YACHT = "YACHT"
    UNKNOWN = "UNKNOWN"
    DARK_VESSEL = "DARK_VESSEL"


@dataclass
class AISMessage:
    mmsi: str
    timestamp: datetime
    message_type: int
    lat: float
    lon: float
    speed_knots: float
    course_deg: float
    heading_deg: float
    vessel_name: Optional[str]
    vessel_type: int
    destination: Optional[str]
    nav_status: int
    raw_nmea: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        payload = asdict(self)
        payload["timestamp"] = _iso(self.timestamp)
        return payload

    def is_underway(self) -> bool:
        return self.nav_status in (0, 2, 3, 4, 6, 7, 8)


@dataclass
class AISVessel:
    mmsi: str
    vessel_name: str
    classification: VesselClassification
    flag_state: str
    imo_number: Optional[str]
    length_meters: float
    beam_meters: float
    last_position: Tuple[float, float]
    last_speed_knots: float
    last_heading_deg: float
    last_seen: datetime
    positions_count: int
    ais_active: bool
    risk_score: float
    track: List[Dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        payload = asdict(self)
        payload["classification"] = self.classification.value
        payload["last_seen"] = _iso(self.last_seen)
        return payload

    def is_dark(self) -> bool:
        if self.positions_count <= 0:
            return False
        age_hours = (datetime.now(timezone.utc) - self.last_seen).total_seconds() / 3600.0
        return (not self.ais_active and age_hours > 1.0) or age_hours > 1.0


@dataclass
class VesselTrack:
    track_id: str
    vessel_id: str
    positions: List[Tuple[float, float]]
    timestamps: List[datetime]
    source: str = "ais"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "track_id": self.track_id,
            "vessel_id": self.vessel_id,
            "positions": self.positions,
            "timestamps": [_iso(ts) for ts in self.timestamps],
            "source": self.source,
        }


@dataclass
class BorderZone:
    zone_id: str
    name: str
    zone_type: str
    polygon: List[Tuple[float, float]]
    threat_level: str
    active_sensors: List[str]

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    def contains_point(self, lat: float, lon: float) -> bool:
        # Tactical border containment uses ray-casting for deterministic offline checks.
        x = lon
        y = lat
        inside = False
        n = len(self.polygon)
        if n < 3:
            return False
        for i in range(n):
            lat_i, lon_i = self.polygon[i]
            lat_j, lon_j = self.polygon[(i - 1) % n]
            xi = lon_i
            yi = lat_i
            xj = lon_j
            yj = lat_j
            intersects = ((yi > y) != (yj > y)) and (
                x < (xj - xi) * (y - yi) / ((yj - yi) if (yj - yi) != 0 else 1e-12) + xi
            )
            if intersects:
                inside = not inside
        return inside


@dataclass
class BorderAlert:
    alert_id: str
    zone_id: str
    timestamp: datetime
    alert_type: str
    severity: str
    position: Tuple[float, float]
    description: str
    vessel_id: Optional[str]
    confidence: float
    evidence: List[Dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        payload = asdict(self)
        payload["timestamp"] = _iso(self.timestamp)
        return payload


@dataclass
class MaritimePicture:
    timestamp: datetime
    region: str
    vessels: List[Dict[str, Any]]
    sar_detections: List[Dict[str, Any]]
    border_alerts: List[Dict[str, Any]]
    zones: List[Dict[str, Any]]
    statistics: Dict[str, Any]

    def to_dict(self) -> Dict[str, Any]:
        payload = asdict(self)
        payload["timestamp"] = _iso(self.timestamp)
        return payload


def make_alert(
    zone_id: str,
    alert_type: str,
    severity: str,
    position: Tuple[float, float],
    description: str,
    vessel_id: Optional[str] = None,
    confidence: float = 0.7,
    evidence: Optional[List[Dict[str, Any]]] = None,
) -> BorderAlert:
    return BorderAlert(
        alert_id=str(uuid4()),
        zone_id=zone_id,
        timestamp=datetime.now(timezone.utc),
        alert_type=alert_type,
        severity=severity,
        position=position,
        description=description,
        vessel_id=vessel_id,
        confidence=confidence,
        evidence=evidence or [],
    )
