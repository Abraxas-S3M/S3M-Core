"""Data models for tactical radar management.

Military context:
These structures model radar assets, scan plots, and fused tracks used by a
command post to build an air picture from distributed sensors.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, Optional, Tuple


def _iso(ts: datetime) -> str:
    return ts.astimezone(timezone.utc).isoformat()


class RadarType(str, Enum):
    GENERIC_3D = "generic_3d"
    AESA = "aesa"
    COUNTER_BATTERY = "counter_battery"
    FIRE_CONTROL = "fire_control"


class RadarBand(str, Enum):
    L = "L"
    S = "S"
    C = "C"
    X = "X"
    KU = "Ku"


class ScanMode(str, Enum):
    VOLUME = "volume"
    SECTOR = "sector"
    TRACK = "track"


class RCSClassification(str, Enum):
    UNKNOWN = "unknown"
    SMALL = "small"
    MEDIUM = "medium"
    LARGE = "large"


class TrackState(str, Enum):
    TENTATIVE = "tentative"
    CONFIRMED = "confirmed"


@dataclass
class RadarConfig:
    name_en: str
    name_ar: str
    radar_type: RadarType
    band: RadarBand
    position: Tuple[float, float, float]
    max_range_m: float
    scan_mode: ScanMode = ScanMode.VOLUME
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        payload = asdict(self)
        payload["radar_type"] = self.radar_type.value
        payload["band"] = self.band.value
        payload["scan_mode"] = self.scan_mode.value
        return payload


@dataclass
class RadarUnit:
    radar_id: str
    config: RadarConfig
    registered_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def to_dict(self) -> Dict[str, Any]:
        return {
            "radar_id": self.radar_id,
            "registered_at": _iso(self.registered_at),
            **self.config.to_dict(),
        }


@dataclass
class RadarStatus:
    radar_id: str
    operational: bool = True
    scans_received: int = 0
    plots_received: int = 0
    plots_correlated: int = 0
    last_scan_time: Optional[datetime] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "radar_id": self.radar_id,
            "operational": self.operational,
            "scans_received": self.scans_received,
            "plots_received": self.plots_received,
            "plots_correlated": self.plots_correlated,
            "last_scan": _iso(self.last_scan_time) if self.last_scan_time else None,
        }


@dataclass
class RadarPlot:
    plot_id: str
    radar_id: str
    position: Tuple[float, float, float]
    rcs_classification: RCSClassification
    correlated_track_id: Optional[str]
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    attributes: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        payload = asdict(self)
        payload["timestamp"] = _iso(self.timestamp)
        payload["rcs_classification"] = self.rcs_classification.value
        return payload


@dataclass
class FusedTrack:
    track_id: str
    state: TrackState
    last_update: datetime
    source_hits: int = 1

    def to_dict(self) -> Dict[str, Any]:
        payload = asdict(self)
        payload["state"] = self.state.value
        payload["last_update"] = _iso(self.last_update)
        return payload

