"""Data models for radar measurement quality and configuration.

Military context:
These models capture sensor-specific quality settings so fusion and fire-control
logic can weight each radar feed according to known tactical accuracy limits.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from math import isfinite


def _validate_non_negative(value: float, *, field_name: str) -> float:
    validated = float(value)
    if not isfinite(validated) or validated < 0.0:
        raise ValueError(f"{field_name} must be a finite non-negative number")
    return validated


class RadarType(str, Enum):
    RPS_82 = "rps_82"
    RPS_202 = "rps_202"
    GENERIC_2D = "generic_2d"
    GENERIC_3D = "generic_3d"
    AESA_WESTERN = "aesa_western"
    AESA_PANEL = "aesa_panel"
    DOPPLER_CW = "doppler_cw"
    CUSTOM = "custom"


@dataclass
class RadarConfig:
    radar_id: str
    radar_type: RadarType = RadarType.CUSTOM
    max_range_m: float = 300_000.0
    range_noise_std_m: float = 0.0
    azimuth_noise_std_deg: float = 0.0
    elevation_noise_std_deg: float = 0.0
    velocity_noise_std_mps: float = 0.0

    def __post_init__(self) -> None:
        if not self.radar_id:
            raise ValueError("radar_id is required")
        self.radar_type = RadarType(self.radar_type)
        self.max_range_m = _validate_non_negative(self.max_range_m, field_name="max_range_m")
        self.range_noise_std_m = _validate_non_negative(
            self.range_noise_std_m,
            field_name="range_noise_std_m",
        )
        self.azimuth_noise_std_deg = _validate_non_negative(
            self.azimuth_noise_std_deg,
            field_name="azimuth_noise_std_deg",
        )
        self.elevation_noise_std_deg = _validate_non_negative(
            self.elevation_noise_std_deg,
            field_name="elevation_noise_std_deg",
        )
        self.velocity_noise_std_mps = _validate_non_negative(
            self.velocity_noise_std_mps,
            field_name="velocity_noise_std_mps",
        )
