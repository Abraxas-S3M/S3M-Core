"""Core models for layered air-defense fire control.

Military context:
These data structures model echeloned air defense behavior so tactical planners
can prioritize long-range interceptors first and preserve close-in systems for
leakers that penetrate outer rings.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from math import hypot
from typing import Optional, Tuple
from uuid import uuid4


class DefenseEchelon(str, Enum):
    """Defense depth rings used for engagement priority."""

    EXTENDED = "extended"
    MEDIUM = "medium"
    SHORT = "short"
    CLOSE = "close"


class EffectorType(str, Enum):
    """Representative effector systems used in tactical templates."""

    THAAD = "THAAD"
    PATRIOT_PAC3 = "PATRIOT_PAC3"
    BUK_FS = "BUK_FS"
    NASAMS = "NASAMS"
    SHORAD = "SHORAD"
    SKYNEX = "SKYNEX"


class EffectorCategory(str, Enum):
    """High-level effector role for allocation policies."""

    SAM_LONG = "sam_long"
    SAM_MEDIUM = "sam_medium"
    SAM_SHORT = "sam_short"
    CIWS_GUN = "ciws_gun"


class EffectorState(str, Enum):
    """Readiness state of an air-defense effector."""

    READY = "ready"
    ENGAGING = "engaging"
    DEPLETED = "depleted"
    MAINTENANCE = "maintenance"


@dataclass
class EngagementEnvelope:
    """Kinematic envelope for legal/physical engagements."""

    min_range_m: float
    max_range_m: float
    min_altitude_m: float
    max_altitude_m: float
    pk_single_shot: float = 0.70
    max_target_speed_mps: Optional[float] = None

    def target_in_envelope(
        self,
        slant_range_m: float,
        altitude_m: float,
        target_speed_mps: Optional[float] = None,
    ) -> bool:
        """Return true if target kinematics are within this weapon envelope."""
        if slant_range_m < self.min_range_m or slant_range_m > self.max_range_m:
            return False
        if altitude_m < self.min_altitude_m or altitude_m > self.max_altitude_m:
            return False
        if (
            self.max_target_speed_mps is not None
            and target_speed_mps is not None
            and target_speed_mps > self.max_target_speed_mps
        ):
            return False
        return True


@dataclass
class DefenseZone:
    """Circular defense zone around a protected center point."""

    echelon: DefenseEchelon
    center: Tuple[float, float, float]
    inner_radius_m: float
    outer_radius_m: float
    min_altitude_m: float
    max_altitude_m: float
    zone_id: str = field(default_factory=lambda: f"zone-{uuid4()}")
    assigned_effector_ids: list[str] = field(default_factory=list)

    def contains_point(self, point: Tuple[float, float, float]) -> bool:
        """Check if a target is inside the tactical ring and altitude gate."""
        dx = point[0] - self.center[0]
        dy = point[1] - self.center[1]
        altitude = point[2]
        range_m = hypot(dx, dy)
        return (
            self.inner_radius_m <= range_m <= self.outer_radius_m
            and self.min_altitude_m <= altitude <= self.max_altitude_m
        )


@dataclass
class Effector:
    """Single fire unit with inventory, geometry, and engagement state."""

    name_en: str
    name_ar: str
    effector_type: EffectorType
    category: EffectorCategory
    echelon: DefenseEchelon
    envelope: EngagementEnvelope
    position: Tuple[float, float, float]
    ammunition_total: int
    ammunition_remaining: int
    effector_id: str = field(default_factory=lambda: f"eff-{uuid4()}")
    state: EffectorState = EffectorState.READY
    assigned_zone_id: Optional[str] = None
    current_target_id: Optional[str] = None
    kills_confirmed: int = 0
    shots_fired: int = 0

    @property
    def is_available(self) -> bool:
        """True when the unit can accept a new tactical engagement."""
        return self.state == EffectorState.READY and self.ammunition_remaining > 0

    @property
    def readiness_score(self) -> float:
        """Simple readiness metric used to rank candidate effectors."""
        if self.ammunition_total <= 0:
            return 0.0
        ammo_ratio = max(0.0, self.ammunition_remaining / self.ammunition_total)
        state_factor = 1.0 if self.state == EffectorState.READY else 0.25
        return ammo_ratio * state_factor

    def can_engage(
        self,
        target_position: Tuple[float, float, float],
        target_speed_mps: Optional[float] = None,
    ) -> bool:
        """Return true when target geometry is inside this effector envelope."""
        if not self.is_available:
            return False
        dx = target_position[0] - self.position[0]
        dy = target_position[1] - self.position[1]
        slant_range_m = hypot(dx, dy)
        return self.envelope.target_in_envelope(
            slant_range_m=slant_range_m,
            altitude_m=target_position[2],
            target_speed_mps=target_speed_mps,
        )

    def begin_engagement(self, target_id: str) -> None:
        """Mark unit as engaging a designated track."""
        if not self.is_available:
            raise ValueError(f"Effector {self.effector_id} is not available")
        self.state = EffectorState.ENGAGING
        self.current_target_id = target_id

    def complete_engagement(self, kill: bool) -> None:
        """Resolve engagement and update tactical inventory/accounting."""
        if self.ammunition_remaining > 0:
            self.ammunition_remaining -= 1
            self.shots_fired += 1
        if kill:
            self.kills_confirmed += 1
        self.current_target_id = None
        self.state = (
            EffectorState.READY
            if self.ammunition_remaining > 0
            else EffectorState.DEPLETED
        )

