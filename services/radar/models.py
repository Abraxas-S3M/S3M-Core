"""Data models for tactical radar sensing and fused tracks.

Military context:
These structures represent tactical radar detections and fused air tracks used
to maintain a layered local air picture in contested low-altitude scenarios.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from math import isfinite
from typing import Tuple
from uuid import uuid4


def _validate_finite(value: float, *, field_name: str) -> float:
    numeric = float(value)
    if not isfinite(numeric):
        raise ValueError(f"{field_name} must be finite")
    return numeric


def _validate_non_negative(value: float, *, field_name: str) -> float:
    numeric = _validate_finite(value, field_name=field_name)
    if numeric < 0.0:
        raise ValueError(f"{field_name} must be non-negative")
    return numeric


def _validate_position(position: Tuple[float, float, float]) -> Tuple[float, float, float]:
    if len(position) != 3:
        raise ValueError("position must contain exactly three coordinates")
    return (
        _validate_finite(position[0], field_name="position_x"),
        _validate_finite(position[1], field_name="position_y"),
        _validate_finite(position[2], field_name="position_z"),
    )


class RadarType(str, Enum):
    RPS_82 = "rps-82"
    RPS_202 = "rps-202"
    AESA = "aesa"


class RCSClassification(str, Enum):
    MICRO_UAV = "micro_uav"
    SHAHED_CLASS_UAV = "shahed_class_uav"
    TACTICAL_UAV = "tactical_uav"
    CRUISE_MISSILE = "cruise_missile_like"
    AIRCRAFT = "aircraft_like"


class TrackState(str, Enum):
    TENTATIVE = "tentative"
    CONFIRMED = "confirmed"


@dataclass(slots=True)
class RadarConfig:
    radar_id: str
    name_en: str
    radar_type: RadarType
    position: Tuple[float, float, float]
    max_range_m: float

    def __post_init__(self) -> None:
        if not self.radar_id:
            raise ValueError("radar_id is required")
        if not self.name_en:
            raise ValueError("name_en is required")
        self.position = _validate_position(self.position)
        self.max_range_m = _validate_non_negative(self.max_range_m, field_name="max_range_m")
        if self.max_range_m == 0.0:
            raise ValueError("max_range_m must be > 0")


@dataclass(slots=True)
class RadarPlot:
    radar_id: str
    range_m: float
    azimuth_deg: float
    elevation_deg: float
    velocity_mps: float
    rcs_dbsm: float
    snr_db: float
    position_cartesian: Tuple[float, float, float]
    rcs_classification: RCSClassification
    classification_confidence: float

    def __post_init__(self) -> None:
        if not self.radar_id:
            raise ValueError("radar_id is required")
        self.range_m = _validate_non_negative(self.range_m, field_name="range_m")
        self.azimuth_deg = _validate_finite(self.azimuth_deg, field_name="azimuth_deg")
        self.elevation_deg = _validate_finite(self.elevation_deg, field_name="elevation_deg")
        self.velocity_mps = _validate_finite(self.velocity_mps, field_name="velocity_mps")
        self.rcs_dbsm = _validate_finite(self.rcs_dbsm, field_name="rcs_dbsm")
        self.snr_db = _validate_finite(self.snr_db, field_name="snr_db")
        self.position_cartesian = _validate_position(self.position_cartesian)
        self.classification_confidence = _validate_finite(
            self.classification_confidence,
            field_name="classification_confidence",
        )
        if not (0.0 <= self.classification_confidence <= 1.0):
            raise ValueError("classification_confidence must be in [0.0, 1.0]")


@dataclass(slots=True)
class FusedTrack:
    position: Tuple[float, float, float]
    velocity: Tuple[float, float, float]
    sensor_sources: list[str]
    classification: str
    state: TrackState
    track_id: str = field(default_factory=lambda: str(uuid4()))

    def __post_init__(self) -> None:
        self.position = _validate_position(self.position)
        self.velocity = _validate_position(self.velocity)
        if not self.sensor_sources:
            raise ValueError("sensor_sources must not be empty")
        if not self.classification:
            raise ValueError("classification is required")
