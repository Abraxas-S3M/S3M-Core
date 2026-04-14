"""Data models for tactical radar ingest and plot quality gating.

Military context:
These structures represent raw and normalized radar detections used by
Layer 02 fusion to maintain air and ground situational awareness in
contested, disconnected environments.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from math import isfinite
from typing import Any, Dict, List


def _validate_finite(value: float, *, field_name: str) -> float:
    value = float(value)
    if not isfinite(value):
        raise ValueError(f"{field_name} must be a finite number")
    return value


@dataclass
class RadarConfig:
    """Configures a radar's admissible detection envelope."""

    min_range_m: float = 0.0
    max_range_m: float = 250_000.0
    has_elevation: bool = False
    min_elevation_deg: float = -10.0
    max_elevation_deg: float = 90.0
    min_detectable_snr_db: float = 5.0

    def __post_init__(self) -> None:
        self.min_range_m = _validate_finite(self.min_range_m, field_name="min_range_m")
        self.max_range_m = _validate_finite(self.max_range_m, field_name="max_range_m")
        self.min_elevation_deg = _validate_finite(self.min_elevation_deg, field_name="min_elevation_deg")
        self.max_elevation_deg = _validate_finite(self.max_elevation_deg, field_name="max_elevation_deg")
        self.min_detectable_snr_db = _validate_finite(
            self.min_detectable_snr_db,
            field_name="min_detectable_snr_db",
        )
        if self.min_range_m < 0.0:
            raise ValueError("min_range_m must be >= 0.0")
        if self.max_range_m <= self.min_range_m:
            raise ValueError("max_range_m must be > min_range_m")
        if self.max_elevation_deg < self.min_elevation_deg:
            raise ValueError("max_elevation_deg must be >= min_elevation_deg")


@dataclass
class RadarPlot:
    """Single normalized radar return for tactical fusion."""

    range_m: float
    azimuth_deg: float
    elevation_deg: float = 0.0
    snr_db: float = 0.0
    radial_velocity_mps: float = 0.0
    metadata: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        self.range_m = _validate_finite(self.range_m, field_name="range_m")
        self.azimuth_deg = _validate_finite(self.azimuth_deg, field_name="azimuth_deg")
        self.elevation_deg = _validate_finite(self.elevation_deg, field_name="elevation_deg")
        self.snr_db = _validate_finite(self.snr_db, field_name="snr_db")
        self.radial_velocity_mps = _validate_finite(self.radial_velocity_mps, field_name="radial_velocity_mps")
        if self.range_m < 0.0:
            raise ValueError("range_m must be >= 0.0")
        if not isinstance(self.metadata, dict):
            raise ValueError("metadata must be a dictionary")


@dataclass
class RadarScan:
    """Radar sweep snapshot containing normalized tactical plots."""

    radar_id: str
    timestamp: datetime
    plots: List[RadarPlot] = field(default_factory=list)

    def __post_init__(self) -> None:
        if not isinstance(self.radar_id, str) or not self.radar_id.strip():
            raise ValueError("radar_id must be a non-empty string")
        if not isinstance(self.timestamp, datetime):
            raise ValueError("timestamp must be a datetime")
        if self.timestamp.tzinfo is None:
            self.timestamp = self.timestamp.replace(tzinfo=timezone.utc)
        if any(not isinstance(plot, RadarPlot) for plot in self.plots):
            raise ValueError("plots must contain only RadarPlot instances")
