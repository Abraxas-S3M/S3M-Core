"""Radar domain models used by tactical reconnaissance services.

Military context:
These data models represent radar sensors feeding the C3 picture during
air-defense rehearsals, where deterministic validation is required to keep
offline simulations on edge hardware trustworthy.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from math import isfinite
from typing import Optional, Tuple
from uuid import uuid4


def _validate_non_negative(value: float, *, field_name: str) -> float:
    value = float(value)
    if not isfinite(value) or value < 0.0:
        raise ValueError(f"{field_name} must be a finite non-negative number")
    return value


def _validate_positive(value: float, *, field_name: str) -> float:
    value = float(value)
    if not isfinite(value) or value <= 0.0:
        raise ValueError(f"{field_name} must be a finite positive number")
    return value


def _validate_position(position: Tuple[float, float, float]) -> Tuple[float, float, float]:
    if len(position) != 3:
        raise ValueError("position must contain exactly three coordinates")
    x, y, z = (float(position[0]), float(position[1]), float(position[2]))
    if not (isfinite(x) and isfinite(y) and isfinite(z)):
        raise ValueError("position coordinates must be finite numbers")
    return (x, y, z)


class RadarBand(str, Enum):
    L_BAND = "l_band"
    S_BAND = "s_band"
    C_BAND = "c_band"
    X_BAND = "x_band"


class RadarType(str, Enum):
    RPS_82 = "rps_82"
    RPS_202 = "rps_202"
    AESA_WESTERN = "aesa_western"


class ScanMode(str, Enum):
    ROTATING = "rotating"
    ELECTRONIC = "electronic"


@dataclass
class RadarConfig:
    name_en: str
    name_ar: str
    radar_type: RadarType
    band: RadarBand
    scan_mode: ScanMode
    position: Tuple[float, float, float]
    max_range_m: float
    min_range_m: float = 0.0
    max_elevation_deg: float = 60.0
    has_elevation: bool = True
    has_doppler: bool = True
    beam_width_az_deg: float = 2.0
    scan_rate_rpm: Optional[float] = None
    update_rate_hz: Optional[float] = None
    min_detectable_rcs_dbsm: float = -10.0
    range_noise_std_m: float = 25.0
    azimuth_noise_std_deg: float = 0.8
    elevation_noise_std_deg: float = 1.0
    radar_id: str = field(default_factory=lambda: str(uuid4()))

    def __post_init__(self) -> None:
        if not self.name_en:
            raise ValueError("name_en is required")
        if not self.name_ar:
            raise ValueError("name_ar is required")
        if not self.radar_id:
            raise ValueError("radar_id is required")

        self.position = _validate_position(self.position)
        self.max_range_m = _validate_positive(self.max_range_m, field_name="max_range_m")
        self.min_range_m = _validate_non_negative(self.min_range_m, field_name="min_range_m")
        if self.max_range_m < self.min_range_m:
            raise ValueError("max_range_m must be >= min_range_m")

        self.max_elevation_deg = float(self.max_elevation_deg)
        if not isfinite(self.max_elevation_deg) or not (0.0 <= self.max_elevation_deg <= 90.0):
            raise ValueError("max_elevation_deg must be within [0.0, 90.0]")

        self.beam_width_az_deg = _validate_positive(self.beam_width_az_deg, field_name="beam_width_az_deg")
        self.range_noise_std_m = _validate_non_negative(self.range_noise_std_m, field_name="range_noise_std_m")
        self.azimuth_noise_std_deg = _validate_non_negative(
            self.azimuth_noise_std_deg,
            field_name="azimuth_noise_std_deg",
        )
        self.elevation_noise_std_deg = _validate_non_negative(
            self.elevation_noise_std_deg,
            field_name="elevation_noise_std_deg",
        )

        self.min_detectable_rcs_dbsm = float(self.min_detectable_rcs_dbsm)
        if not isfinite(self.min_detectable_rcs_dbsm):
            raise ValueError("min_detectable_rcs_dbsm must be finite")

        if self.scan_mode is ScanMode.ROTATING:
            if self.scan_rate_rpm is None:
                raise ValueError("scan_rate_rpm is required for rotating radars")
            self.scan_rate_rpm = _validate_positive(self.scan_rate_rpm, field_name="scan_rate_rpm")
        elif self.scan_mode is ScanMode.ELECTRONIC:
            if self.update_rate_hz is None:
                raise ValueError("update_rate_hz is required for electronic radars")
            self.update_rate_hz = _validate_positive(self.update_rate_hz, field_name="update_rate_hz")
