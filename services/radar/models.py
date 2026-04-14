"""Radar domain models for tactical sensor reporting."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Optional, Tuple


class RadarType(str, Enum):
    """Supported radar families for force-protection sensing."""

    RPS_82 = "RPS_82"
    RPS_202 = "RPS_202"
    GENERIC_2D = "GENERIC_2D"
    GENERIC_3D = "GENERIC_3D"
    AESA_WESTERN = "AESA_WESTERN"
    AESA_PANEL = "AESA_PANEL"


class RadarBand(str, Enum):
    """RF operating bands relevant to battlefield radar catalogs."""

    L = "L"
    S = "S"
    C = "C"
    X = "X"
    KU = "KU"


class RCSClassification(str, Enum):
    """RCS-derived classes used for initial tactical threat triage."""

    UNKNOWN = "UNKNOWN"
    MICRO = "MICRO"
    SMALL = "SMALL"
    MEDIUM = "MEDIUM"
    LARGE = "LARGE"


@dataclass
class RadarConfig:
    """Static configuration describing one registered radar asset."""

    radar_id: str
    radar_type: RadarType
    band: RadarBand
    max_range_m: float
    name_en: str = "Unnamed Radar"
    position_m: Tuple[float, float, float] = (0.0, 0.0, 0.0)
    clutter_snr_threshold_db: float = 3.0

    def __post_init__(self) -> None:
        if not isinstance(self.radar_id, str) or not self.radar_id.strip():
            raise ValueError("radar_id must be a non-empty string")
        if not isinstance(self.radar_type, RadarType):
            raise ValueError("radar_type must be a RadarType")
        if not isinstance(self.band, RadarBand):
            raise ValueError("band must be a RadarBand")
        if not isinstance(self.max_range_m, (int, float)) or float(self.max_range_m) <= 0:
            raise ValueError("max_range_m must be a positive number")
        self.max_range_m = float(self.max_range_m)
        if not isinstance(self.name_en, str) or not self.name_en.strip():
            raise ValueError("name_en must be a non-empty string")
        if not isinstance(self.position_m, tuple) or len(self.position_m) != 3:
            raise ValueError("position_m must be a tuple of (x, y, z)")
        if not all(isinstance(v, (int, float)) for v in self.position_m):
            raise ValueError("position_m values must be numeric")
        self.position_m = (
            float(self.position_m[0]),
            float(self.position_m[1]),
            float(self.position_m[2]),
        )
        if not isinstance(self.clutter_snr_threshold_db, (int, float)):
            raise ValueError("clutter_snr_threshold_db must be numeric")
        self.clutter_snr_threshold_db = float(self.clutter_snr_threshold_db)


@dataclass
class RadarPlot:
    """Single radar plot after adapter parsing."""

    plot_id: str
    range_m: float
    azimuth_deg: float
    elevation_deg: float = 0.0
    rcs_dbsm: float = -30.0
    radial_velocity_mps: float = 0.0
    snr_db: float = 0.0
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    position_cartesian: Optional[Tuple[float, float, float]] = None
    rcs_classification: RCSClassification = RCSClassification.UNKNOWN
    correlated_track_id: Optional[str] = None

    def __post_init__(self) -> None:
        if not isinstance(self.plot_id, str) or not self.plot_id.strip():
            raise ValueError("plot_id must be a non-empty string")
        for field_name in ("range_m", "azimuth_deg", "elevation_deg", "rcs_dbsm", "radial_velocity_mps", "snr_db"):
            value = getattr(self, field_name)
            if not isinstance(value, (int, float)):
                raise ValueError(f"{field_name} must be numeric")
            setattr(self, field_name, float(value))
        if self.range_m < 0.0:
            raise ValueError("range_m must be non-negative")
        if not isinstance(self.timestamp, datetime):
            raise ValueError("timestamp must be datetime")
        if self.position_cartesian is not None:
            if not isinstance(self.position_cartesian, tuple) or len(self.position_cartesian) != 3:
                raise ValueError("position_cartesian must be a tuple of (x, y, z)")
            if not all(isinstance(v, (int, float)) for v in self.position_cartesian):
                raise ValueError("position_cartesian values must be numeric")
            self.position_cartesian = (
                float(self.position_cartesian[0]),
                float(self.position_cartesian[1]),
                float(self.position_cartesian[2]),
            )
        if not isinstance(self.rcs_classification, RCSClassification):
            raise ValueError("rcs_classification must be an RCSClassification")
        if self.correlated_track_id is not None and not isinstance(self.correlated_track_id, str):
            raise ValueError("correlated_track_id must be a string or None")


@dataclass
class RadarScan:
    """One scan burst from a radar for COP update cycles."""

    radar_id: str
    timestamp: datetime
    plots: list[RadarPlot]

    def __post_init__(self) -> None:
        if not isinstance(self.radar_id, str) or not self.radar_id.strip():
            raise ValueError("radar_id must be a non-empty string")
        if not isinstance(self.timestamp, datetime):
            raise ValueError("timestamp must be datetime")
        if not isinstance(self.plots, list):
            raise ValueError("plots must be a list")
        if any(not isinstance(plot, RadarPlot) for plot in self.plots):
            raise ValueError("plots entries must be RadarPlot instances")


@dataclass
class RadarStatus:
    """Operational counters for radar readiness monitoring."""

    radar_id: str
    operational: bool = True
    scans_received: int = 0
    plots_received: int = 0
    plots_correlated: int = 0
    last_scan_time: Optional[datetime] = None

    def __post_init__(self) -> None:
        if not isinstance(self.radar_id, str) or not self.radar_id.strip():
            raise ValueError("radar_id must be a non-empty string")

