"""Radar domain models for tactical multi-radar integration.

Military context:
These typed dataclasses define the standardized radar contract that allows
heterogeneous surveillance assets to feed one fused air picture without
vendor-specific assumptions in Layer 02.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from math import isfinite
from typing import Any, Dict, List, Optional, Sequence, Tuple
from uuid import uuid4


def _finite(value: float, *, field_name: str) -> float:
    converted = float(value)
    if not isfinite(converted):
        raise ValueError(f"{field_name} must be a finite number")
    return converted


def _non_negative(value: float, *, field_name: str) -> float:
    converted = _finite(value, field_name=field_name)
    if converted < 0.0:
        raise ValueError(f"{field_name} must be non-negative")
    return converted


def _bounded_probability(value: float, *, field_name: str) -> float:
    converted = _finite(value, field_name=field_name)
    if not (0.0 <= converted <= 1.0):
        raise ValueError(f"{field_name} must be in [0.0, 1.0]")
    return converted


def _normalize_azimuth(azimuth_deg: float) -> float:
    value = _finite(azimuth_deg, field_name="azimuth_deg")
    return value % 360.0


def _validate_timestamp(value: datetime, *, field_name: str) -> datetime:
    if not isinstance(value, datetime):
        raise ValueError(f"{field_name} must be a datetime")
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value


class RadarType(str, Enum):
    """Supported radar family identifiers for adapter dispatch."""

    GENERIC_2D = "GENERIC_2D"
    GENERIC_3D = "GENERIC_3D"
    RPS_82 = "RPS_82"
    RPS_202 = "RPS_202"
    WESTERN_AESA = "WESTERN_AESA"

    @classmethod
    def from_value(cls, value: str | "RadarType") -> "RadarType":
        if isinstance(value, RadarType):
            return value
        if isinstance(value, str):
            normalized = value.strip().upper()
            if normalized in cls.__members__:
                return cls[normalized]
        raise ValueError(f"Invalid radar type: {value}")


class RadarBand(str, Enum):
    """Electromagnetic band for radar performance/noise tuning."""

    L_BAND = "L_BAND"
    S_BAND = "S_BAND"
    C_BAND = "C_BAND"
    X_BAND = "X_BAND"
    KU_BAND = "KU_BAND"

    @classmethod
    def from_value(cls, value: str | "RadarBand") -> "RadarBand":
        if isinstance(value, RadarBand):
            return value
        if isinstance(value, str):
            normalized = value.strip().upper()
            if normalized in cls.__members__:
                return cls[normalized]
        raise ValueError(f"Invalid radar band: {value}")


class ScanMode(str, Enum):
    """Radar tactical scan patterns."""

    SEARCH = "SEARCH"
    SECTOR = "SECTOR"
    VOLUME = "VOLUME"
    TRACK_WHILE_SCAN = "TRACK_WHILE_SCAN"

    @classmethod
    def from_value(cls, value: str | "ScanMode") -> "ScanMode":
        if isinstance(value, ScanMode):
            return value
        if isinstance(value, str):
            normalized = value.strip().upper()
            if normalized in cls.__members__:
                return cls[normalized]
        raise ValueError(f"Invalid scan mode: {value}")


class RadarStatus(str, Enum):
    """Operational status for command-post readiness reporting."""

    ONLINE = "ONLINE"
    DEGRADED = "DEGRADED"
    OFFLINE = "OFFLINE"
    MAINTENANCE = "MAINTENANCE"

    @classmethod
    def from_value(cls, value: str | "RadarStatus") -> "RadarStatus":
        if isinstance(value, RadarStatus):
            return value
        if isinstance(value, str):
            normalized = value.strip().upper()
            if normalized in cls.__members__:
                return cls[normalized]
        raise ValueError(f"Invalid radar status: {value}")


class RCSClassification(str, Enum):
    """Tactical class labels inferred from radar cross section."""

    SMALL_UAV = "SMALL_UAV"
    MEDIUM_UAV = "MEDIUM_UAV"
    CRUISE_MISSILE = "CRUISE_MISSILE"
    HELICOPTER = "HELICOPTER"
    FIGHTER_AIRCRAFT = "FIGHTER_AIRCRAFT"
    LARGE_AIRCRAFT = "LARGE_AIRCRAFT"
    BALLISTIC_TARGET = "BALLISTIC_TARGET"
    UNKNOWN = "UNKNOWN"


@dataclass
class RadarPlot:
    """One raw radar detection in polar coordinates from one scan."""

    range_m: float
    azimuth_deg: float
    elevation_deg: float
    radial_velocity_mps: float
    rcs_m2: float
    snr_db: float
    confidence: float = 1.0
    plot_id: str = field(default_factory=lambda: str(uuid4()))
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    metadata: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not isinstance(self.plot_id, str) or not self.plot_id.strip():
            raise ValueError("plot_id must be a non-empty string")
        self.timestamp = _validate_timestamp(self.timestamp, field_name="timestamp")
        self.range_m = _non_negative(self.range_m, field_name="range_m")
        self.azimuth_deg = _normalize_azimuth(self.azimuth_deg)
        self.elevation_deg = _finite(self.elevation_deg, field_name="elevation_deg")
        self.radial_velocity_mps = _finite(self.radial_velocity_mps, field_name="radial_velocity_mps")
        self.rcs_m2 = _non_negative(self.rcs_m2, field_name="rcs_m2")
        self.snr_db = _finite(self.snr_db, field_name="snr_db")
        self.confidence = _bounded_probability(self.confidence, field_name="confidence")
        if not isinstance(self.metadata, dict):
            raise ValueError("metadata must be a dictionary")


@dataclass
class RadarScan:
    """Set of plots produced by one tactical radar sweep."""

    radar_id: str
    scan_mode: ScanMode
    plots: List[RadarPlot]
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    scan_id: str = field(default_factory=lambda: str(uuid4()))
    scan_index: int = 0
    status: RadarStatus = RadarStatus.ONLINE

    def __post_init__(self) -> None:
        if not isinstance(self.radar_id, str) or not self.radar_id.strip():
            raise ValueError("radar_id must be a non-empty string")
        self.scan_mode = ScanMode.from_value(self.scan_mode)
        self.timestamp = _validate_timestamp(self.timestamp, field_name="timestamp")
        if not isinstance(self.scan_id, str) or not self.scan_id.strip():
            raise ValueError("scan_id must be a non-empty string")
        if not isinstance(self.scan_index, int) or self.scan_index < 0:
            raise ValueError("scan_index must be a non-negative integer")
        self.status = RadarStatus.from_value(self.status)
        if not isinstance(self.plots, list):
            raise ValueError("plots must be a list")
        if any(not isinstance(plot, RadarPlot) for plot in self.plots):
            raise ValueError("plots must contain RadarPlot objects")


@dataclass
class RadarConfig:
    """Static/dynamic configuration for one radar adapter instance."""

    radar_id: str
    radar_type: RadarType
    radar_band: RadarBand
    name_en: str
    name_ar: str
    position_lla: Tuple[float, float, float]
    orientation_deg: Tuple[float, float, float] = (0.0, 0.0, 0.0)
    scan_rate_hz: float = 1.0
    beam_width_az_deg: float = 2.0
    beam_width_el_deg: float = 4.0
    min_range_m: float = 100.0
    max_range_m: float = 120_000.0
    doppler_resolution_mps: float = 1.5
    nominal_detection_probability: float = 0.9
    detection_probability_curve: Sequence[Tuple[float, float]] = field(default_factory=tuple)
    status: RadarStatus = RadarStatus.ONLINE
    metadata: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not isinstance(self.radar_id, str) or not self.radar_id.strip():
            raise ValueError("radar_id must be a non-empty string")
        self.radar_type = RadarType.from_value(self.radar_type)
        self.radar_band = RadarBand.from_value(self.radar_band)
        if not isinstance(self.name_en, str) or not self.name_en.strip():
            raise ValueError("name_en must be a non-empty string")
        if not isinstance(self.name_ar, str) or not self.name_ar.strip():
            raise ValueError("name_ar must be a non-empty string")
        if not isinstance(self.position_lla, tuple) or len(self.position_lla) != 3:
            raise ValueError("position_lla must be a tuple of (lat_deg, lon_deg, alt_m)")
        lat = _finite(self.position_lla[0], field_name="position_lla[0]")
        lon = _finite(self.position_lla[1], field_name="position_lla[1]")
        alt = _finite(self.position_lla[2], field_name="position_lla[2]")
        if not (-90.0 <= lat <= 90.0):
            raise ValueError("position_lla latitude must be in [-90, 90]")
        if not (-180.0 <= lon <= 180.0):
            raise ValueError("position_lla longitude must be in [-180, 180]")
        self.position_lla = (lat, lon, alt)
        if not isinstance(self.orientation_deg, tuple) or len(self.orientation_deg) != 3:
            raise ValueError("orientation_deg must be a tuple of (yaw, pitch, roll)")
        self.orientation_deg = (
            _finite(self.orientation_deg[0], field_name="orientation_deg[0]"),
            _finite(self.orientation_deg[1], field_name="orientation_deg[1]"),
            _finite(self.orientation_deg[2], field_name="orientation_deg[2]"),
        )
        self.scan_rate_hz = _non_negative(self.scan_rate_hz, field_name="scan_rate_hz")
        if self.scan_rate_hz <= 0.0:
            raise ValueError("scan_rate_hz must be greater than zero")
        self.beam_width_az_deg = _non_negative(self.beam_width_az_deg, field_name="beam_width_az_deg")
        self.beam_width_el_deg = _non_negative(self.beam_width_el_deg, field_name="beam_width_el_deg")
        if self.beam_width_az_deg <= 0.0 or self.beam_width_el_deg <= 0.0:
            raise ValueError("beam widths must be greater than zero")
        self.min_range_m = _non_negative(self.min_range_m, field_name="min_range_m")
        self.max_range_m = _non_negative(self.max_range_m, field_name="max_range_m")
        if self.max_range_m <= self.min_range_m:
            raise ValueError("max_range_m must be greater than min_range_m")
        self.doppler_resolution_mps = _non_negative(self.doppler_resolution_mps, field_name="doppler_resolution_mps")
        self.nominal_detection_probability = _bounded_probability(
            self.nominal_detection_probability,
            field_name="nominal_detection_probability",
        )
        if not isinstance(self.detection_probability_curve, Sequence):
            raise ValueError("detection_probability_curve must be a sequence")
        normalized_curve: List[Tuple[float, float]] = []
        for idx, pair in enumerate(self.detection_probability_curve):
            if not isinstance(pair, (tuple, list)) or len(pair) != 2:
                raise ValueError(
                    f"detection_probability_curve[{idx}] must be a (snr_db, probability) pair"
                )
            snr_db = _finite(pair[0], field_name=f"detection_probability_curve[{idx}][0]")
            prob = _bounded_probability(pair[1], field_name=f"detection_probability_curve[{idx}][1]")
            normalized_curve.append((snr_db, prob))
        normalized_curve.sort(key=lambda item: item[0])
        self.detection_probability_curve = tuple(normalized_curve)
        self.status = RadarStatus.from_value(self.status)
        if not isinstance(self.metadata, dict):
            raise ValueError("metadata must be a dictionary")


@dataclass
class PlotCorrelation:
    """Association between two plots across consecutive scans."""

    radar_id: str
    previous_plot_id: str
    current_plot_id: str
    dt_seconds: float
    spatial_distance_m: float
    radial_velocity_delta_mps: float
    score: float
    correlation_id: str = field(default_factory=lambda: str(uuid4()))

    def __post_init__(self) -> None:
        if not isinstance(self.radar_id, str) or not self.radar_id.strip():
            raise ValueError("radar_id must be a non-empty string")
        if not isinstance(self.previous_plot_id, str) or not self.previous_plot_id.strip():
            raise ValueError("previous_plot_id must be a non-empty string")
        if not isinstance(self.current_plot_id, str) or not self.current_plot_id.strip():
            raise ValueError("current_plot_id must be a non-empty string")
        self.dt_seconds = _non_negative(self.dt_seconds, field_name="dt_seconds")
        self.spatial_distance_m = _non_negative(self.spatial_distance_m, field_name="spatial_distance_m")
        self.radial_velocity_delta_mps = abs(_finite(self.radial_velocity_delta_mps, field_name="radial_velocity_delta_mps"))
        self.score = _bounded_probability(self.score, field_name="score")
        if not isinstance(self.correlation_id, str) or not self.correlation_id.strip():
            raise ValueError("correlation_id must be a non-empty string")
