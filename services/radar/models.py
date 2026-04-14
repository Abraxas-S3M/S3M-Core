"""Data models for radar target tracks and RCS classes.

Military context:
These structures carry tactical radar returns into downstream kill-chain logic
where classification confidence influences engagement sequencing.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from math import isfinite
from typing import Optional, Tuple


def _validate_finite(value: float, *, field_name: str) -> float:
    cast_value = float(value)
    if not isfinite(cast_value):
        raise ValueError(f"{field_name} must be a finite number")
    return cast_value


class RCSClassification(str, Enum):
    CLUTTER = "CLUTTER"
    SMALL_UAV = "SMALL_UAV"
    MEDIUM_UAV = "MEDIUM_UAV"
    LARGE_UAV = "LARGE_UAV"
    CRUISE_MISSILE = "CRUISE_MISSILE"
    FIGHTER = "FIGHTER"
    HELICOPTER = "HELICOPTER"
    LARGE_AIRCRAFT = "LARGE_AIRCRAFT"
    BALLISTIC = "BALLISTIC"
    UNKNOWN = "UNKNOWN"


@dataclass
class RadarPlot:
    """Single radar plot used for tactical air target evaluation."""

    rcs_linear_m2: float
    radial_velocity_mps: float
    position_cartesian: Optional[Tuple[float, float, float]] = None
    rcs_classification: RCSClassification = RCSClassification.UNKNOWN
    classification_confidence: float = 0.0

    def __post_init__(self) -> None:
        self.rcs_linear_m2 = _validate_finite(self.rcs_linear_m2, field_name="rcs_linear_m2")
        self.radial_velocity_mps = _validate_finite(
            self.radial_velocity_mps,
            field_name="radial_velocity_mps",
        )
        self.classification_confidence = _validate_finite(
            self.classification_confidence,
            field_name="classification_confidence",
        )
        if self.rcs_linear_m2 < 0:
            raise ValueError("rcs_linear_m2 must be non-negative")
        if not 0.0 <= self.classification_confidence <= 1.0:
            raise ValueError("classification_confidence must be in [0.0, 1.0]")
        if self.position_cartesian is not None:
            if len(self.position_cartesian) != 3:
                raise ValueError("position_cartesian must contain exactly three values")
            x, y, z = self.position_cartesian
            self.position_cartesian = (
                _validate_finite(x, field_name="position_cartesian[0]"),
                _validate_finite(y, field_name="position_cartesian[1]"),
                _validate_finite(z, field_name="position_cartesian[2]"),
            )
