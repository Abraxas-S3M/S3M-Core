"""Data models for genome-enhanced threat trajectory prediction.

Military context:
These structures carry the threat-track forecast that air-defense operators use
to prioritize engagements when adversary doctrine suggests non-random behavior.
"""

from __future__ import annotations

from dataclasses import dataclass
from math import isfinite
from typing import Optional, Tuple


def _validate_vector3(
    value: Tuple[float, float, float],
    *,
    field_name: str,
) -> Tuple[float, float, float]:
    if len(value) != 3:
        raise ValueError(f"{field_name} must contain exactly three coordinates")
    x, y, z = (float(value[0]), float(value[1]), float(value[2]))
    if not (isfinite(x) and isfinite(y) and isfinite(z)):
        raise ValueError(f"{field_name} coordinates must be finite numbers")
    return (x, y, z)


def _validate_non_negative(value: float, *, field_name: str) -> float:
    numeric = float(value)
    if not isfinite(numeric) or numeric < 0.0:
        raise ValueError(f"{field_name} must be a finite non-negative number")
    return numeric


def _clamp_unit_interval(value: float, *, field_name: str) -> float:
    numeric = float(value)
    if not isfinite(numeric):
        raise ValueError(f"{field_name} must be finite")
    return max(0.0, min(1.0, numeric))


@dataclass
class ThreatTrajectoryPrediction:
    """Genome-biased trajectory forecast for one tracked threat."""

    track_id: str
    target_classification: str
    genome_match: Optional[str]
    genome_confidence: float
    current_position: Tuple[float, float, float]
    current_velocity: Tuple[float, float, float]
    current_speed_mps: float
    current_heading_deg: float
    predicted_30s: Optional[Tuple[float, float, float]]
    predicted_60s: Optional[Tuple[float, float, float]]
    predicted_120s: Optional[Tuple[float, float, float]]
    range_to_asset_now_m: float
    range_to_asset_30s_m: float
    range_to_asset_60s_m: float
    range_to_asset_120s_m: float
    time_to_zone_entry_s: float
    time_to_asset_s: float
    prediction_confidence: float
    genome_bias_applied: bool
    behavioral_pattern: str = ""

    def __post_init__(self) -> None:
        if not self.track_id:
            raise ValueError("track_id is required")
        if not self.target_classification:
            raise ValueError("target_classification is required")

        self.genome_confidence = _clamp_unit_interval(
            self.genome_confidence,
            field_name="genome_confidence",
        )
        self.current_position = _validate_vector3(
            self.current_position,
            field_name="current_position",
        )
        self.current_velocity = _validate_vector3(
            self.current_velocity,
            field_name="current_velocity",
        )
        self.current_speed_mps = _validate_non_negative(
            self.current_speed_mps,
            field_name="current_speed_mps",
        )

        heading = float(self.current_heading_deg)
        if not isfinite(heading):
            raise ValueError("current_heading_deg must be a finite number")
        self.current_heading_deg = heading % 360.0

        if self.predicted_30s is not None:
            self.predicted_30s = _validate_vector3(self.predicted_30s, field_name="predicted_30s")
        if self.predicted_60s is not None:
            self.predicted_60s = _validate_vector3(self.predicted_60s, field_name="predicted_60s")
        if self.predicted_120s is not None:
            self.predicted_120s = _validate_vector3(self.predicted_120s, field_name="predicted_120s")

        self.range_to_asset_now_m = _validate_non_negative(
            self.range_to_asset_now_m,
            field_name="range_to_asset_now_m",
        )
        self.range_to_asset_30s_m = _validate_non_negative(
            self.range_to_asset_30s_m,
            field_name="range_to_asset_30s_m",
        )
        self.range_to_asset_60s_m = _validate_non_negative(
            self.range_to_asset_60s_m,
            field_name="range_to_asset_60s_m",
        )
        self.range_to_asset_120s_m = _validate_non_negative(
            self.range_to_asset_120s_m,
            field_name="range_to_asset_120s_m",
        )
        self.time_to_zone_entry_s = _validate_non_negative(
            self.time_to_zone_entry_s,
            field_name="time_to_zone_entry_s",
        )
        self.time_to_asset_s = _validate_non_negative(
            self.time_to_asset_s,
            field_name="time_to_asset_s",
        )
        self.prediction_confidence = _clamp_unit_interval(
            self.prediction_confidence,
            field_name="prediction_confidence",
        )
