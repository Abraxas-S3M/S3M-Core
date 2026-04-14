"""Data models for layered air-defense fire allocation.

Military context:
These models formalize tactical engagement state for Krechet-style fire
distribution so layered echelons can engage hostile air threats deterministically
in disconnected combat conditions.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from math import isfinite, sqrt
from typing import List, Optional, Tuple


class DefenseEchelon(str, Enum):
    """Layered defense bands used for doctrine-driven target engagement."""

    EXTENDED = "extended"
    MEDIUM = "medium"
    SHORT = "short"
    CLOSE = "close"


class EffectorCategory(str, Enum):
    """Mission category of an effector for target suitability matching."""

    SAM_MEDIUM = "sam_medium"
    SAM_SHORT = "sam_short"
    CIWS_GUN = "ciws_gun"
    MANPADS = "manpads"
    INTERCEPTOR_DRONE = "interceptor_drone"
    ELECTRONIC_WARFARE = "electronic_warfare"


class EffectorType(str, Enum):
    """Concrete effector type for operator-readable audit messages."""

    SAM_9M96 = "sam_9m96"
    SAM_PANTSIR = "sam_pantsir"
    CIWS_30MM = "ciws_30mm"
    MANPADS_IGLA = "manpads_igla"
    INTERCEPTOR_UAV = "interceptor_uav"
    EW_JAMMER = "ew_jammer"


class EffectorState(str, Enum):
    """Lifecycle state for whether an effector can accept engagements."""

    READY = "ready"
    ENGAGED = "engaged"
    RELOADING = "reloading"
    MAINTENANCE = "maintenance"
    OFFLINE = "offline"


@dataclass(slots=True)
class EffectorEnvelope:
    """Kinematic constraints used to validate tactical intercept feasibility."""

    max_range_m: float
    min_range_m: float
    min_altitude_m: float
    max_altitude_m: float
    max_target_speed_mps: float
    pk_single_shot: float

    def __post_init__(self) -> None:
        if self.max_range_m <= 0 or not isfinite(self.max_range_m):
            raise ValueError("max_range_m must be finite and positive")
        if self.min_range_m < 0 or self.min_range_m >= self.max_range_m:
            raise ValueError("min_range_m must be >= 0 and less than max_range_m")
        if self.max_altitude_m <= self.min_altitude_m:
            raise ValueError("max_altitude_m must be greater than min_altitude_m")
        if self.max_target_speed_mps <= 0 or not isfinite(self.max_target_speed_mps):
            raise ValueError("max_target_speed_mps must be finite and positive")
        if not (0.0 <= self.pk_single_shot <= 1.0):
            raise ValueError("pk_single_shot must be between 0.0 and 1.0")

    def can_engage(
        self, slant_range_m: float, altitude_m: float, target_speed_mps: float
    ) -> bool:
        """Return whether target geometry is inside intercept envelope."""
        return (
            self.min_range_m <= slant_range_m <= self.max_range_m
            and self.min_altitude_m <= altitude_m <= self.max_altitude_m
            and target_speed_mps <= self.max_target_speed_mps
        )


@dataclass(slots=True)
class AirDefenseZone:
    """Circular tactical zone describing one layer of defended airspace."""

    zone_id: str
    name: str
    echelon: DefenseEchelon
    center_position: Tuple[float, float, float]
    min_radius_m: float
    max_radius_m: float

    def __post_init__(self) -> None:
        if not self.zone_id.strip():
            raise ValueError("zone_id must be non-empty")
        if self.min_radius_m < 0 or self.max_radius_m <= self.min_radius_m:
            raise ValueError("zone radii must satisfy 0 <= min < max")
        _validate_position(self.center_position)

    def contains_target(self, target_position: Tuple[float, float, float]) -> bool:
        """Return true when target lies inside this tactical defense ring."""
        _validate_position(target_position)
        dx = target_position[0] - self.center_position[0]
        dy = target_position[1] - self.center_position[1]
        radial_distance = sqrt(dx * dx + dy * dy)
        return self.min_radius_m <= radial_distance <= self.max_radius_m


@dataclass(slots=True)
class Effector:
    """Individual firing unit with envelope and readiness metadata."""

    effector_id: str
    name_en: str
    effector_type: EffectorType
    category: EffectorCategory
    echelon: DefenseEchelon
    state: EffectorState
    zone_id: str
    position: Tuple[float, float, float]
    envelope: EffectorEnvelope
    readiness_score: float
    ammunition_total: int
    ammunition_remaining: int
    current_target_id: Optional[str] = None

    def __post_init__(self) -> None:
        if not self.effector_id.strip():
            raise ValueError("effector_id must be non-empty")
        if not self.zone_id.strip():
            raise ValueError("zone_id must be non-empty")
        _validate_position(self.position)
        if not (0.0 <= self.readiness_score <= 1.0):
            raise ValueError("readiness_score must be between 0.0 and 1.0")
        if self.ammunition_total < 0:
            raise ValueError("ammunition_total must be >= 0")
        if self.ammunition_remaining < 0:
            raise ValueError("ammunition_remaining must be >= 0")
        if self.ammunition_remaining > self.ammunition_total:
            raise ValueError("ammunition_remaining cannot exceed ammunition_total")

    def is_available(self) -> bool:
        """Combat-ready means ready state, positive ammo, and nonzero readiness."""
        return (
            self.state == EffectorState.READY
            and self.ammunition_remaining > 0
            and self.readiness_score > 0.0
        )

    def range_to(self, target_position: Tuple[float, float, float]) -> float:
        """Return 3D slant range used for fire-control decision logic."""
        _validate_position(target_position)
        dx = target_position[0] - self.position[0]
        dy = target_position[1] - self.position[1]
        dz = target_position[2] - self.position[2]
        return sqrt(dx * dx + dy * dy + dz * dz)

    def can_engage(
        self, target_position: Tuple[float, float, float], target_speed_mps: float
    ) -> bool:
        """Return true if this effector can currently prosecute the target."""
        if target_speed_mps < 0:
            return False
        if not self.is_available():
            return False
        slant_range = self.range_to(target_position)
        altitude_m = target_position[2]
        return self.envelope.can_engage(slant_range, altitude_m, target_speed_mps)

    def begin_engagement(self, target_id: str) -> None:
        """Transition to engaged state after tactical fire assignment."""
        if not target_id.strip():
            raise ValueError("target_id must be non-empty")
        self.current_target_id = target_id
        if self.ammunition_remaining > 0:
            self.ammunition_remaining -= 1
        self.state = EffectorState.ENGAGED


@dataclass(slots=True)
class TargetAllocation:
    """Auditable result of assigning one target to one effector."""

    target_id: str
    target_position: Tuple[float, float, float]
    target_speed_mps: float
    target_classification: str
    effector_id: str
    effector_type: EffectorType
    echelon: DefenseEchelon
    zone_id: str
    slant_range_m: float
    pk_estimate: float
    suitability_score: float
    reasoning: str
    fallback_effector_ids: List[str] = field(default_factory=list)


@dataclass(slots=True)
class AllocationResult:
    """Top-level allocation response consumed by kill-chain services."""

    allocated: bool
    reasoning: str
    allocation: Optional[TargetAllocation] = None
    alternatives_count: int = 0
    echelon_used: Optional[DefenseEchelon] = None


def _validate_position(position: Tuple[float, float, float]) -> None:
    if len(position) != 3:
        raise ValueError("position must contain three coordinates")
    for axis in position:
        if not isfinite(axis):
            raise ValueError("position coordinates must be finite")
