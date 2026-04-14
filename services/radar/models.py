"""Data models for radar detections and radar site configuration."""

from __future__ import annotations

from dataclasses import dataclass
import math
from typing import Optional, Tuple


def _require_finite(value: float, field_name: str) -> None:
    if not isinstance(value, (int, float)) or not math.isfinite(float(value)):
        raise ValueError(f"{field_name} must be a finite number")


@dataclass
class RadarPlot:
    """Single radar detection represented in native polar coordinates."""

    range_m: float
    azimuth_deg: float
    elevation_deg: float
    position_cartesian: Optional[Tuple[float, float, float]] = None
    position_wgs84: Optional[Tuple[float, float, float]] = None

    def __post_init__(self) -> None:
        _require_finite(self.range_m, "range_m")
        _require_finite(self.azimuth_deg, "azimuth_deg")
        _require_finite(self.elevation_deg, "elevation_deg")
        if self.range_m < 0.0:
            raise ValueError("range_m must be >= 0")
        if not -90.0 <= self.elevation_deg <= 90.0:
            raise ValueError("elevation_deg must be between -90 and 90")


@dataclass
class RadarConfig:
    """Radar sensor mounting and georeference metadata."""

    position: Tuple[float, float, float]
    heading_deg: float = 0.0
    uses_wgs84: bool = False

    def __post_init__(self) -> None:
        _require_finite(self.heading_deg, "heading_deg")
        if len(self.position) != 3:
            raise ValueError("position must be a 3-tuple")
        _require_finite(self.position[0], "position[0]")
        _require_finite(self.position[1], "position[1]")
        _require_finite(self.position[2], "position[2]")

        if self.uses_wgs84:
            lat, lon, _ = self.position
            if not -90.0 <= lat <= 90.0:
                raise ValueError("WGS84 latitude must be between -90 and 90")
            if not -180.0 <= lon <= 180.0:
                raise ValueError("WGS84 longitude must be between -180 and 180")
