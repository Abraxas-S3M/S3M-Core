"""Core radar data models for tactical air-defense sensing.

Military context:
These structures normalize heterogeneous radar feeds into a common track/plot
schema so C2 and engagement logic can reason about contacts consistently.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from math import isfinite


def _to_finite_float(value: float | int, *, field_name: str) -> float:
    parsed = float(value)
    if not isfinite(parsed):
        raise ValueError(f"{field_name} must be a finite number")
    return parsed


class RadarType(str, Enum):
    """Known radar families used by the tactical picture."""

    RPS_202 = "RPS_202"


class RadarBand(str, Enum):
    """RF operating bands used by supported sensors."""

    S_BAND = "S_BAND"


class ScanMode(str, Enum):
    """Scan behavior informing coverage and revisit assumptions."""

    ROTATING = "ROTATING"


@dataclass
class RadarConfig:
    """Operational envelope and noise model for a radar type."""

    radar_id: str = "rps202-default"
    name_en: str = ""
    name_ar: str = ""
    radar_type: RadarType = RadarType.RPS_202
    band: RadarBand = RadarBand.S_BAND
    scan_mode: ScanMode = ScanMode.ROTATING
    max_range_m: float = 0.0
    min_range_m: float = 0.0
    max_elevation_deg: float = 0.0
    has_elevation: bool = True
    has_doppler: bool = True
    beam_width_az_deg: float = 0.0
    beam_width_el_deg: float = 0.0
    scan_rate_rpm: float = 0.0
    min_detectable_rcs_dbsm: float = 0.0
    range_resolution_m: float = 0.0
    range_noise_std_m: float = 0.0
    azimuth_noise_std_deg: float = 0.0
    elevation_noise_std_deg: float = 0.0

    def __post_init__(self) -> None:
        if not self.radar_id:
            raise ValueError("radar_id is required")
        if isinstance(self.radar_type, str):
            self.radar_type = RadarType(self.radar_type)
        if isinstance(self.band, str):
            self.band = RadarBand(self.band)
        if isinstance(self.scan_mode, str):
            self.scan_mode = ScanMode(self.scan_mode)

        self.max_range_m = _to_finite_float(self.max_range_m, field_name="max_range_m")
        self.min_range_m = _to_finite_float(self.min_range_m, field_name="min_range_m")
        if self.max_range_m < 0.0 or self.min_range_m < 0.0:
            raise ValueError("range limits must be non-negative")
        if self.max_range_m < self.min_range_m:
            raise ValueError("max_range_m must be >= min_range_m")

        self.max_elevation_deg = _to_finite_float(self.max_elevation_deg, field_name="max_elevation_deg")
        self.beam_width_az_deg = _to_finite_float(self.beam_width_az_deg, field_name="beam_width_az_deg")
        self.beam_width_el_deg = _to_finite_float(self.beam_width_el_deg, field_name="beam_width_el_deg")
        self.scan_rate_rpm = _to_finite_float(self.scan_rate_rpm, field_name="scan_rate_rpm")
        self.min_detectable_rcs_dbsm = _to_finite_float(
            self.min_detectable_rcs_dbsm,
            field_name="min_detectable_rcs_dbsm",
        )
        self.range_resolution_m = _to_finite_float(self.range_resolution_m, field_name="range_resolution_m")
        self.range_noise_std_m = _to_finite_float(self.range_noise_std_m, field_name="range_noise_std_m")
        self.azimuth_noise_std_deg = _to_finite_float(self.azimuth_noise_std_deg, field_name="azimuth_noise_std_deg")
        self.elevation_noise_std_deg = _to_finite_float(
            self.elevation_noise_std_deg,
            field_name="elevation_noise_std_deg",
        )


@dataclass
class RadarPlot:
    """Single radar return in a normalized tactical coordinate space."""

    radar_id: str
    timestamp: datetime
    range_m: float
    azimuth_deg: float
    elevation_deg: float
    radial_velocity_mps: float
    rcs_dbsm: float
    snr_db: float

    def __post_init__(self) -> None:
        if not self.radar_id:
            raise ValueError("radar_id is required")
        if isinstance(self.timestamp, str):
            self.timestamp = datetime.fromisoformat(self.timestamp.replace("Z", "+00:00"))
        if self.timestamp.tzinfo is None:
            self.timestamp = self.timestamp.replace(tzinfo=timezone.utc)

        self.range_m = _to_finite_float(self.range_m, field_name="range_m")
        self.azimuth_deg = _to_finite_float(self.azimuth_deg, field_name="azimuth_deg")
        self.elevation_deg = _to_finite_float(self.elevation_deg, field_name="elevation_deg")
        self.radial_velocity_mps = _to_finite_float(self.radial_velocity_mps, field_name="radial_velocity_mps")
        self.rcs_dbsm = _to_finite_float(self.rcs_dbsm, field_name="rcs_dbsm")
        self.snr_db = _to_finite_float(self.snr_db, field_name="snr_db")

        if self.range_m < 0.0:
            raise ValueError("range_m must be non-negative")
