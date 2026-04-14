"""Data models for autonomous interceptor guidance and engagement outcomes.

Military context:
These structures keep guidance state explicit and auditable so battery crews can
reconstruct each engagement decision cycle during tactical after-action review.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from math import isfinite
from typing import Tuple


Vec3 = Tuple[float, float, float]


def _validate_vec3(value: Vec3, *, field_name: str) -> Vec3:
    if len(value) != 3:
        raise ValueError(f"{field_name} must contain exactly three coordinates")
    x, y, z = (float(value[0]), float(value[1]), float(value[2]))
    if not (isfinite(x) and isfinite(y) and isfinite(z)):
        raise ValueError(f"{field_name} coordinates must be finite numbers")
    return (x, y, z)


def _validate_non_negative(value: float, *, field_name: str) -> float:
    parsed = float(value)
    if not isfinite(parsed) or parsed < 0.0:
        raise ValueError(f"{field_name} must be a finite non-negative number")
    return parsed


class InterceptorState(str, Enum):
    READY = "ready"
    ASSIGNED = "assigned"
    LAUNCHED = "launched"
    TRACKING = "tracking"
    TERMINAL = "terminal"
    COMPLETE = "complete"


@dataclass
class InterceptorConfig:
    interceptor_id: str
    max_speed_mps: float = 350.0
    max_acceleration_mps2: float = 60.0
    seeker_acquisition_range_m: float = 3_500.0
    hit_radius_m: float = 25.0
    fuel_endurance_s: float = 120.0

    def __post_init__(self) -> None:
        if not self.interceptor_id:
            raise ValueError("interceptor_id is required")
        self.max_speed_mps = _validate_non_negative(self.max_speed_mps, field_name="max_speed_mps")
        self.max_acceleration_mps2 = _validate_non_negative(
            self.max_acceleration_mps2,
            field_name="max_acceleration_mps2",
        )
        self.seeker_acquisition_range_m = _validate_non_negative(
            self.seeker_acquisition_range_m,
            field_name="seeker_acquisition_range_m",
        )
        self.hit_radius_m = _validate_non_negative(self.hit_radius_m, field_name="hit_radius_m")
        self.fuel_endurance_s = _validate_non_negative(
            self.fuel_endurance_s,
            field_name="fuel_endurance_s",
        )
        if self.max_acceleration_mps2 == 0.0:
            raise ValueError("max_acceleration_mps2 must be > 0")


@dataclass
class GuidanceSolution:
    interceptor_id: str
    target_id: str
    interceptor_state: InterceptorState
    command_acceleration_mps2: Vec3
    range_to_target_m: float
    closing_speed_mps: float
    should_fire_fuze: bool
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def __post_init__(self) -> None:
        if not self.interceptor_id:
            raise ValueError("interceptor_id is required")
        if not self.target_id:
            raise ValueError("target_id is required")
        self.command_acceleration_mps2 = _validate_vec3(
            self.command_acceleration_mps2,
            field_name="command_acceleration_mps2",
        )
        self.range_to_target_m = _validate_non_negative(
            self.range_to_target_m,
            field_name="range_to_target_m",
        )
        self.closing_speed_mps = float(self.closing_speed_mps)
        if not isfinite(self.closing_speed_mps):
            raise ValueError("closing_speed_mps must be finite")


@dataclass
class InterceptResult:
    interceptor_id: str
    target_id: str
    outcome: str
    final_state: InterceptorState
    final_range_m: float
    cycles_completed: int
    completed_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def __post_init__(self) -> None:
        if not self.interceptor_id:
            raise ValueError("interceptor_id is required")
        if not self.target_id:
            raise ValueError("target_id is required")
        if self.outcome not in {"hit", "miss", "aborted", "incomplete"}:
            raise ValueError("outcome must be one of: hit, miss, aborted, incomplete")
        self.final_range_m = _validate_non_negative(self.final_range_m, field_name="final_range_m")
        self.cycles_completed = int(self.cycles_completed)
        if self.cycles_completed < 0:
            raise ValueError("cycles_completed must be >= 0")
