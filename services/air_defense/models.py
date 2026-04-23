"""Data models for layered air-defense target allocation.

Military context:
These structures encode the tactical state needed to execute layered
engagements (drone -> missile -> gun -> EW) while preserving auditable
decision history for after-action review.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from math import isfinite, sqrt
from typing import Optional, Tuple
from uuid import uuid4


def _validate_position(position: Tuple[float, float, float]) -> Tuple[float, float, float]:
    if len(position) != 3:
        raise ValueError("position must contain exactly three coordinates")
    x, y, z = (float(position[0]), float(position[1]), float(position[2]))
    if not (isfinite(x) and isfinite(y) and isfinite(z)):
        raise ValueError("position coordinates must be finite numbers")
    return (x, y, z)


def _validate_non_negative(value: float, *, field_name: str) -> float:
    value = float(value)
    if not isfinite(value) or value < 0.0:
        raise ValueError(f"{field_name} must be a finite non-negative number")
    return value


class EffectorCategory(str, Enum):
    INTERCEPTOR_DRONE = "interceptor_drone"
    SAM_MEDIUM = "sam_medium"
    SAM_SHORT = "sam_short"
    CIWS_GUN = "ciws_gun"
    MANPADS = "manpads"
    ELECTRONIC_WARFARE = "electronic_warfare"


class EffectorState(str, Enum):
    AVAILABLE = "available"
    ENGAGING = "engaging"
    OFFLINE = "offline"


@dataclass
class EffectorEnvelope:
    min_range_m: float = 0.0
    max_range_m: float = 10_000.0
    max_target_speed_mps: Optional[float] = None
    pk_single_shot: float = 0.5

    def __post_init__(self) -> None:
        self.min_range_m = _validate_non_negative(self.min_range_m, field_name="min_range_m")
        self.max_range_m = _validate_non_negative(self.max_range_m, field_name="max_range_m")
        if self.max_range_m < self.min_range_m:
            raise ValueError("max_range_m must be >= min_range_m")
        if self.max_target_speed_mps is not None:
            self.max_target_speed_mps = _validate_non_negative(
                self.max_target_speed_mps,
                field_name="max_target_speed_mps",
            )
        self.pk_single_shot = float(self.pk_single_shot)
        if not isfinite(self.pk_single_shot) or not (0.0 <= self.pk_single_shot <= 1.0):
            raise ValueError("pk_single_shot must be in [0.0, 1.0]")


@dataclass
class Effector:
    effector_id: str
    name_en: str
    effector_type: str
    category: EffectorCategory
    echelon: str
    position: Tuple[float, float, float]
    envelope: EffectorEnvelope
    readiness_score: float = 1.0
    assigned_zone_id: Optional[str] = None
    state: EffectorState = EffectorState.AVAILABLE
    current_target_id: Optional[str] = None

    def __post_init__(self) -> None:
        if not self.effector_id:
            raise ValueError("effector_id is required")
        if not self.name_en:
            raise ValueError("name_en is required")
        self.position = _validate_position(self.position)
        self.readiness_score = float(self.readiness_score)
        if not isfinite(self.readiness_score) or not (0.0 <= self.readiness_score <= 1.0):
            raise ValueError("readiness_score must be in [0.0, 1.0]")

    def range_to(self, target_position: Tuple[float, float, float]) -> float:
        tx, ty, tz = _validate_position(target_position)
        sx, sy, sz = self.position
        return sqrt((tx - sx) ** 2 + (ty - sy) ** 2 + (tz - sz) ** 2)

    def can_engage(self, target_position: Tuple[float, float, float], target_speed_mps: float) -> bool:
        if self.state is not EffectorState.AVAILABLE:
            return False
        if self.readiness_score <= 0.0:
            return False

        speed = _validate_non_negative(target_speed_mps, field_name="target_speed_mps")
        range_m = self.range_to(target_position)
        if range_m < self.envelope.min_range_m or range_m > self.envelope.max_range_m:
            return False
        if self.envelope.max_target_speed_mps is not None and speed > self.envelope.max_target_speed_mps:
            return False
        return True

    def begin_engagement(self, target_id: str) -> None:
        if not target_id:
            raise ValueError("target_id is required")
        if self.state is EffectorState.OFFLINE:
            raise RuntimeError(f"Effector {self.effector_id} is offline")
        self.current_target_id = target_id
        self.state = EffectorState.ENGAGING

    def complete_engagement(self, kill: bool) -> None:
        del kill  # Kill/miss disposition is handled by higher-level C2 logs.
        if self.state is not EffectorState.OFFLINE:
            self.state = EffectorState.AVAILABLE
        self.current_target_id = None


@dataclass
class TargetAllocation:
    target_id: str
    target_position: Tuple[float, float, float]
    target_speed_mps: float
    target_classification: str
    effector_id: str
    effector_type: str
    echelon: str
    zone_id: str
    slant_range_m: float
    pk_estimate: float
    suitability_score: float
    reasoning: str
    attempts: int = 0
    max_attempts: int = 3
    allocation_id: str = field(default_factory=lambda: str(uuid4()))
    status: str = "allocated"
    fallback_effector_ids: list[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        if not self.target_id:
            raise ValueError("target_id is required")
        if not self.effector_id:
            raise ValueError("effector_id is required")
        self.target_position = _validate_position(self.target_position)
        self.target_speed_mps = _validate_non_negative(
            self.target_speed_mps,
            field_name="target_speed_mps",
        )
        self.slant_range_m = _validate_non_negative(self.slant_range_m, field_name="slant_range_m")
        self.pk_estimate = float(self.pk_estimate)
        self.suitability_score = float(self.suitability_score)
        if not isfinite(self.pk_estimate) or not (0.0 <= self.pk_estimate <= 1.0):
            raise ValueError("pk_estimate must be in [0.0, 1.0]")
        if not isfinite(self.suitability_score):
            raise ValueError("suitability_score must be finite")
        if self.attempts < 0:
            raise ValueError("attempts must be >= 0")
        if self.max_attempts <= 0:
            raise ValueError("max_attempts must be > 0")


@dataclass
class AllocationResult:
    allocated: bool
    allocation: Optional[TargetAllocation] = None
    reasoning: str = ""
    echelon_used: Optional[str] = None


class DefenseEchelon(str, Enum):
    POINT = "POINT"
    SHORAD = "SHORAD"
    MRAD = "MRAD"
    HIMAD = "HIMAD"
    STRATEGIC = "STRATEGIC"


@dataclass
class DefenseZone:
    zone_id: str
    echelon: DefenseEchelon
    center_lat: float
    center_lon: float
    radius_km: float
    active: bool = True


class EffectorType(str, Enum):
    MISSILE = "MISSILE"
    GUN = "GUN"
    LASER = "LASER"
    EW = "EW"
    DECOY = "DECOY"


@dataclass
class EngagementEnvelope:
    min_range_km: float
    max_range_km: float
    min_alt_m: float
    max_alt_m: float
    max_speed_mach: float


@dataclass
class AirDefenseUnit:
    unit_id: str
    name: str
    zone_id: str
    effector_type: EffectorType
    envelope: EngagementEnvelope
    ammo_count: int
    ready: bool = True
