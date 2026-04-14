"""Data models for tactical radar ingestion and normalization."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from math import isfinite


def _coerce_float(value: float, *, field_name: str) -> float:
    number = float(value)
    if not isfinite(number):
        raise ValueError(f"{field_name} must be a finite number")
    return number


def _coerce_non_negative(value: float, *, field_name: str) -> float:
    number = _coerce_float(value, field_name=field_name)
    if number < 0.0:
        raise ValueError(f"{field_name} must be >= 0")
    return number


class RadarBand(str, Enum):
    L_BAND = "l_band"
    S_BAND = "s_band"
    C_BAND = "c_band"
    X_BAND = "x_band"
    KU_BAND = "ku_band"


class RadarType(str, Enum):
    GENERIC_2D = "generic_2d"
    GENERIC_3D = "generic_3d"


class ScanMode(str, Enum):
    ROTATING = "rotating"
    SECTOR = "sector"
    ELECTRONIC = "electronic"


@dataclass
class RadarConfig:
    radar_id: str = "generic_2d_radar"
    name_en: str = "Radar"
    name_ar: str = "رادار"
    radar_type: RadarType = RadarType.GENERIC_2D
    band: RadarBand = RadarBand.S_BAND
    scan_mode: ScanMode = ScanMode.ROTATING
    max_range_m: float = 80_000.0
    min_range_m: float = 0.0
    has_elevation: bool = False
    has_doppler: bool = False
    beam_width_az_deg: float = 1.0
    scan_rate_rpm: float = 6.0
    range_noise_std_m: float = 100.0
    azimuth_noise_std_deg: float = 1.0

    def __post_init__(self) -> None:
        if not self.radar_id:
            raise ValueError("radar_id is required")
        if not self.name_en:
            raise ValueError("name_en is required")
        self.max_range_m = _coerce_non_negative(self.max_range_m, field_name="max_range_m")
        self.min_range_m = _coerce_non_negative(self.min_range_m, field_name="min_range_m")
        if self.min_range_m > self.max_range_m:
            raise ValueError("min_range_m must be <= max_range_m")
        self.beam_width_az_deg = _coerce_non_negative(
            self.beam_width_az_deg,
            field_name="beam_width_az_deg",
        )
        self.scan_rate_rpm = _coerce_non_negative(self.scan_rate_rpm, field_name="scan_rate_rpm")
        self.range_noise_std_m = _coerce_non_negative(
            self.range_noise_std_m,
            field_name="range_noise_std_m",
        )
        self.azimuth_noise_std_deg = _coerce_non_negative(
            self.azimuth_noise_std_deg,
            field_name="azimuth_noise_std_deg",
        )


@dataclass
class RadarPlot:
    radar_id: str
    timestamp: datetime
    range_m: float
    azimuth_deg: float
    elevation_deg: float
    radial_velocity_mps: float = 0.0
    rcs_dbsm: float = 0.0
    snr_db: float = 15.0
    signal_strength: float = 0.0

    def __post_init__(self) -> None:
        if not self.radar_id:
            raise ValueError("radar_id is required")
        if not isinstance(self.timestamp, datetime):
            raise ValueError("timestamp must be a datetime")
        if self.timestamp.tzinfo is None:
            self.timestamp = self.timestamp.replace(tzinfo=timezone.utc)
        self.range_m = _coerce_non_negative(self.range_m, field_name="range_m")
        self.azimuth_deg = _coerce_float(self.azimuth_deg, field_name="azimuth_deg")
        self.elevation_deg = _coerce_float(self.elevation_deg, field_name="elevation_deg")
        self.radial_velocity_mps = _coerce_float(
            self.radial_velocity_mps,
            field_name="radial_velocity_mps",
        )
        self.rcs_dbsm = _coerce_float(self.rcs_dbsm, field_name="rcs_dbsm")
        self.snr_db = _coerce_float(self.snr_db, field_name="snr_db")
        self.signal_strength = _coerce_float(self.signal_strength, field_name="signal_strength")
