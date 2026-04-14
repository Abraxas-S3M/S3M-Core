"""Data models for tactical radar ingestion and track normalization.

Military context:
These models represent near-real-time radar plots used by forward
surveillance elements to feed command-and-control picture generation.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from math import isfinite


def _validate_finite(value: float, *, field_name: str) -> float:
    parsed = float(value)
    if not isfinite(parsed):
        raise ValueError(f"{field_name} must be a finite number")
    return parsed


class RadarType(str, Enum):
    RPS_82 = "rps_82"


class RadarBand(str, Enum):
    X_BAND = "x_band"


class ScanMode(str, Enum):
    ROTATING = "rotating"
    SECTOR = "sector"


@dataclass
class RadarConfig:
    radar_id: str = "rps82-default"
    name_en: str = ""
    name_ar: str = ""
    radar_type: RadarType = RadarType.RPS_82
    band: RadarBand = RadarBand.X_BAND
    scan_mode: ScanMode = ScanMode.ROTATING
    max_range_m: float = 20_000.0
    min_range_m: float = 0.0
    max_elevation_deg: float = 60.0
    has_elevation: bool = True
    has_doppler: bool = True
    beam_width_az_deg: float = 2.5
    beam_width_el_deg: float = 3.0
    scan_rate_rpm: float = 12.0
    min_detectable_rcs_dbsm: float = -15.0
    range_resolution_m: float = 75.0
    range_noise_std_m: float = 75.0
    azimuth_noise_std_deg: float = 1.0
    elevation_noise_std_deg: float = 2.0

    def __post_init__(self) -> None:
        if not isinstance(self.radar_id, str) or not self.radar_id.strip():
            raise ValueError("radar_id is required")
        if not isinstance(self.name_en, str) or not self.name_en.strip():
            raise ValueError("name_en is required")
        self.max_range_m = _validate_finite(self.max_range_m, field_name="max_range_m")
        self.min_range_m = _validate_finite(self.min_range_m, field_name="min_range_m")
        if self.max_range_m <= 0.0:
            raise ValueError("max_range_m must be positive")
        if self.min_range_m < 0.0:
            raise ValueError("min_range_m must be non-negative")
        if self.max_range_m < self.min_range_m:
            raise ValueError("max_range_m must be >= min_range_m")
        self.max_elevation_deg = _validate_finite(self.max_elevation_deg, field_name="max_elevation_deg")
        self.beam_width_az_deg = _validate_finite(self.beam_width_az_deg, field_name="beam_width_az_deg")
        self.beam_width_el_deg = _validate_finite(self.beam_width_el_deg, field_name="beam_width_el_deg")
        self.scan_rate_rpm = _validate_finite(self.scan_rate_rpm, field_name="scan_rate_rpm")
        self.min_detectable_rcs_dbsm = _validate_finite(
            self.min_detectable_rcs_dbsm,
            field_name="min_detectable_rcs_dbsm",
        )
        self.range_resolution_m = _validate_finite(self.range_resolution_m, field_name="range_resolution_m")
        self.range_noise_std_m = _validate_finite(self.range_noise_std_m, field_name="range_noise_std_m")
        self.azimuth_noise_std_deg = _validate_finite(
            self.azimuth_noise_std_deg,
            field_name="azimuth_noise_std_deg",
        )
        self.elevation_noise_std_deg = _validate_finite(
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

    def __post_init__(self) -> None:
        if not isinstance(self.radar_id, str) or not self.radar_id.strip():
            raise ValueError("radar_id is required")
        if not isinstance(self.timestamp, datetime):
            raise ValueError("timestamp must be a datetime")
        if self.timestamp.tzinfo is None:
            self.timestamp = self.timestamp.replace(tzinfo=timezone.utc)
        else:
            self.timestamp = self.timestamp.astimezone(timezone.utc)

        self.range_m = _validate_finite(self.range_m, field_name="range_m")
        if self.range_m < 0.0:
            raise ValueError("range_m must be non-negative")
        self.azimuth_deg = _validate_finite(self.azimuth_deg, field_name="azimuth_deg")
        self.elevation_deg = _validate_finite(self.elevation_deg, field_name="elevation_deg")
        self.radial_velocity_mps = _validate_finite(self.radial_velocity_mps, field_name="radial_velocity_mps")
        self.rcs_dbsm = _validate_finite(self.rcs_dbsm, field_name="rcs_dbsm")
        self.snr_db = _validate_finite(self.snr_db, field_name="snr_db")
