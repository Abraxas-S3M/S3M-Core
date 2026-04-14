"""Data models for tactical radar surveillance ingest.

Military context:
These types represent sensor configuration and per-scan returns used to build
an auditable air picture for command-and-control decisions.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from math import isfinite


class RadarType(str, Enum):
    GENERIC_3D = "generic_3d"


class RadarBand(str, Enum):
    L_BAND = "L"
    S_BAND = "S"
    C_BAND = "C"
    X_BAND = "X"
    KU_BAND = "Ku"


class ScanMode(str, Enum):
    ROTATING = "rotating"
    ELECTRONIC = "electronic"
    SECTOR = "sector"


def _finite_float(value: float, *, field_name: str) -> float:
    parsed = float(value)
    if not isfinite(parsed):
        raise ValueError(f"{field_name} must be a finite number")
    return parsed


@dataclass
class RadarConfig:
    radar_id: str = "generic_3d"
    name_en: str = "Generic 3D Surveillance Radar"
    name_ar: str = "رادار مراقبة ثلاثي الأبعاد"
    radar_type: RadarType = RadarType.GENERIC_3D
    band: RadarBand = RadarBand.S_BAND
    scan_mode: ScanMode = ScanMode.ROTATING
    max_range_m: float = 60_000.0
    min_range_m: float = 300.0
    has_elevation: bool = True
    has_doppler: bool = True
    beam_width_az_deg: float = 1.5
    beam_width_el_deg: float = 2.0
    scan_rate_rpm: float = 6.0
    range_noise_std_m: float = 60.0
    azimuth_noise_std_deg: float = 0.8
    elevation_noise_std_deg: float = 1.0

    def __post_init__(self) -> None:
        if not str(self.radar_id).strip():
            raise ValueError("radar_id is required")
        self.max_range_m = _finite_float(self.max_range_m, field_name="max_range_m")
        self.min_range_m = _finite_float(self.min_range_m, field_name="min_range_m")
        if self.max_range_m < 0 or self.min_range_m < 0:
            raise ValueError("range limits must be non-negative")
        if self.max_range_m < self.min_range_m:
            raise ValueError("max_range_m must be >= min_range_m")
        self.beam_width_az_deg = _finite_float(self.beam_width_az_deg, field_name="beam_width_az_deg")
        self.beam_width_el_deg = _finite_float(self.beam_width_el_deg, field_name="beam_width_el_deg")
        self.scan_rate_rpm = _finite_float(self.scan_rate_rpm, field_name="scan_rate_rpm")
        self.range_noise_std_m = _finite_float(self.range_noise_std_m, field_name="range_noise_std_m")
        self.azimuth_noise_std_deg = _finite_float(
            self.azimuth_noise_std_deg,
            field_name="azimuth_noise_std_deg",
        )
        self.elevation_noise_std_deg = _finite_float(
            self.elevation_noise_std_deg,
            field_name="elevation_noise_std_deg",
        )


@dataclass
class RadarPlot:
    radar_id: str
    timestamp: datetime
    range_m: float
    azimuth_deg: float
    elevation_deg: float
    radial_velocity_mps: float
    rcs_dbsm: float
    snr_db: float
    signal_strength: float

    def __post_init__(self) -> None:
        if isinstance(self.timestamp, str):
            self.timestamp = datetime.fromisoformat(self.timestamp.replace("Z", "+00:00"))
        if self.timestamp.tzinfo is None:
            self.timestamp = self.timestamp.replace(tzinfo=timezone.utc)
        self.range_m = _finite_float(self.range_m, field_name="range_m")
        if self.range_m < 0.0:
            raise ValueError("range_m must be non-negative")
        self.azimuth_deg = _finite_float(self.azimuth_deg, field_name="azimuth_deg") % 360.0
        self.elevation_deg = _finite_float(self.elevation_deg, field_name="elevation_deg")
        if not -90.0 <= self.elevation_deg <= 90.0:
            raise ValueError("elevation_deg must be between -90 and 90")
        self.radial_velocity_mps = _finite_float(
            self.radial_velocity_mps,
            field_name="radial_velocity_mps",
        )
        self.rcs_dbsm = _finite_float(self.rcs_dbsm, field_name="rcs_dbsm")
        self.snr_db = _finite_float(self.snr_db, field_name="snr_db")
        self.signal_strength = _finite_float(self.signal_strength, field_name="signal_strength")
