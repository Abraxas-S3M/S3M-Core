"""Interceptor guidance data models for Krechet engagement control.

Military context:
These types define state and geometry values used by the interceptor guidance
state machine that transitions from launch through autonomous terminal handoff.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import math


class InterceptorState(str, Enum):
    """Lifecycle states for a single interceptor sortie."""

    PRELAUNCH = "prelaunch"
    LAUNCHED = "launched"
    RADAR_ACQUIRED = "radar_acquired"
    MIDCOURSE_GUIDED = "midcourse_guided"
    TERMINAL_APPROACH = "terminal_approach"
    AUTONOMOUS_HANDOFF = "autonomous_handoff"
    ENGAGED = "engaged"
    MISS = "miss"
    LOST = "lost"
    RTB = "rtb"


class GuidancePhase(str, Enum):
    """Guidance control phases mapped to interceptor mission timing."""

    BOOST = "boost"
    MIDCOURSE = "midcourse"
    TERMINAL = "terminal"
    AUTONOMOUS = "autonomous"
    POST_ENGAGE = "post_engage"


@dataclass
class HandoffCriteria:
    """Range and quality thresholds for transitioning guidance authority."""

    terminal_range_m: float = 500.0
    handoff_range_m: float = 250.0
    min_closing_velocity_mps: float = 25.0
    max_miss_distance_m: float = 35.0

    def __post_init__(self) -> None:
        for field_name in (
            "terminal_range_m",
            "handoff_range_m",
            "min_closing_velocity_mps",
            "max_miss_distance_m",
        ):
            value = float(getattr(self, field_name))
            if not math.isfinite(value) or value <= 0.0:
                raise ValueError(f"{field_name} must be a finite positive value")
            setattr(self, field_name, value)
        if self.handoff_range_m >= self.terminal_range_m:
            raise ValueError("handoff_range_m must be less than terminal_range_m")


@dataclass
class InterceptGeometry:
    """Realtime intercept geometry metrics from seeker and fire-control tracks."""

    range_m: float
    closing_velocity_mps: float
    predicted_miss_distance_m: float

    def __post_init__(self) -> None:
        self.range_m = float(self.range_m)
        self.closing_velocity_mps = float(self.closing_velocity_mps)
        self.predicted_miss_distance_m = float(self.predicted_miss_distance_m)
        if not math.isfinite(self.range_m) or self.range_m < 0.0:
            raise ValueError("range_m must be a finite non-negative value")
        if not math.isfinite(self.closing_velocity_mps):
            raise ValueError("closing_velocity_mps must be a finite value")
        if not math.isfinite(self.predicted_miss_distance_m) or self.predicted_miss_distance_m < 0.0:
            raise ValueError("predicted_miss_distance_m must be a finite non-negative value")
