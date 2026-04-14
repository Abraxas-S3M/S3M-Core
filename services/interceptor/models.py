"""Data models for interceptor guidance geometry.

Military context:
These fields are consumed by tactical guidance logic at radar update cadence.
Input validation is strict to prevent malformed telemetry from propagating into
fire-control decisions.
"""

from __future__ import annotations

from dataclasses import dataclass
from math import isfinite


def _validate_finite(value: float, *, field_name: str) -> float:
    parsed = float(value)
    if not isfinite(parsed):
        raise ValueError(f"{field_name} must be a finite number")
    return parsed


def _validate_non_negative(value: float, *, field_name: str) -> float:
    parsed = _validate_finite(value, field_name=field_name)
    if parsed < 0.0:
        raise ValueError(f"{field_name} must be non-negative")
    return parsed


@dataclass
class InterceptGeometry:
    """Guidance geometry snapshot for one interceptor/target update."""

    range_m: float
    closing_velocity_mps: float
    time_to_intercept_s: float
    line_of_sight_az_deg: float
    line_of_sight_el_deg: float
    los_rate_az_dps: float
    los_rate_el_dps: float
    lead_angle_deg: float
    predicted_miss_distance_m: float
    aspect_angle_deg: float
    crossing_angle_deg: float

    def __post_init__(self) -> None:
        self.range_m = _validate_non_negative(self.range_m, field_name="range_m")
        self.closing_velocity_mps = _validate_finite(
            self.closing_velocity_mps,
            field_name="closing_velocity_mps",
        )
        self.time_to_intercept_s = _validate_non_negative(
            self.time_to_intercept_s,
            field_name="time_to_intercept_s",
        )
        self.line_of_sight_az_deg = _validate_finite(
            self.line_of_sight_az_deg,
            field_name="line_of_sight_az_deg",
        ) % 360.0
        self.line_of_sight_el_deg = _validate_finite(
            self.line_of_sight_el_deg,
            field_name="line_of_sight_el_deg",
        )
        if not -90.0 <= self.line_of_sight_el_deg <= 90.0:
            raise ValueError("line_of_sight_el_deg must be between -90 and 90")
        self.los_rate_az_dps = _validate_finite(self.los_rate_az_dps, field_name="los_rate_az_dps")
        self.los_rate_el_dps = _validate_finite(self.los_rate_el_dps, field_name="los_rate_el_dps")
        self.lead_angle_deg = _validate_finite(self.lead_angle_deg, field_name="lead_angle_deg")
        if not -90.0 <= self.lead_angle_deg <= 90.0:
            raise ValueError("lead_angle_deg must be between -90 and 90")
        self.predicted_miss_distance_m = _validate_non_negative(
            self.predicted_miss_distance_m,
            field_name="predicted_miss_distance_m",
        )
        self.aspect_angle_deg = _validate_finite(self.aspect_angle_deg, field_name="aspect_angle_deg")
        if not 0.0 <= self.aspect_angle_deg <= 180.0:
            raise ValueError("aspect_angle_deg must be between 0 and 180")
        self.crossing_angle_deg = _validate_finite(self.crossing_angle_deg, field_name="crossing_angle_deg")
        if not 0.0 <= self.crossing_angle_deg <= 180.0:
            raise ValueError("crossing_angle_deg must be between 0 and 180")
