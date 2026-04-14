"""Core models for tactical air-defense effector orchestration.

Military context:
Typed structures for batteries and launchers under command-and-control (C2)
so allocation logic can reason about echelon, availability, and engagement
geometry in a deterministic way during contested airspace operations.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from math import sqrt
from typing import Tuple


class EffectorCategory(str, Enum):
    """High-level functional category in layered air defense doctrine."""

    MISSILE = "MISSILE"
    GUN = "GUN"
    EW = "EW"
    LASER = "LASER"


class DefenseEchelon(str, Enum):
    """Defensive layer within strategic-to-point protection hierarchy."""

    STRATEGIC = "STRATEGIC"
    THEATER = "THEATER"
    OPERATIONAL = "OPERATIONAL"
    POINT = "POINT"


class EffectorType(str, Enum):
    """Platform class used for target assignment compatibility checks."""

    SAM = "SAM"
    SHORAD = "SHORAD"
    CIWS = "CIWS"
    EW = "EW"
    DIRECTED_ENERGY = "DIRECTED_ENERGY"


class EffectorState(str, Enum):
    """Operational readiness state for fire-distribution decisions."""

    READY = "READY"
    ENGAGING = "ENGAGING"
    RELOADING = "RELOADING"
    DEGRADED = "DEGRADED"
    OFFLINE = "OFFLINE"


def _normalize_position(position: tuple[float, ...]) -> Tuple[float, float, float]:
    if not isinstance(position, tuple) or len(position) not in {2, 3}:
        raise ValueError("position must be a tuple of length 2 or 3")
    if len(position) == 2:
        x, y = position
        z = 0.0
    else:
        x, y, z = position
    try:
        return (float(x), float(y), float(z))
    except (TypeError, ValueError) as exc:
        raise ValueError("position values must be numeric") from exc


@dataclass
class Effector:
    """Air-defense effector under C2 control."""

    effector_id: str
    category: EffectorCategory
    echelon: DefenseEchelon
    effector_type: EffectorType
    state: EffectorState = EffectorState.READY
    assigned_zone_id: str | None = None
    position: tuple[float, ...] = (0.0, 0.0, 0.0)
    engagement_range_m: float = 10000.0
    min_range_m: float = 0.0
    max_target_speed_mps: float = 5000.0
    ammunition_total: int = 0
    ammunition_remaining: int = 0

    def __post_init__(self) -> None:
        self.effector_id = str(self.effector_id).strip()
        if not self.effector_id:
            raise ValueError("effector_id must be a non-empty string")
        self.category = EffectorCategory(self.category)
        self.echelon = DefenseEchelon(self.echelon)
        self.state = EffectorState(self.state)
        self.effector_type = EffectorType(self.effector_type)
        self.position = _normalize_position(self.position)
        self.engagement_range_m = float(self.engagement_range_m)
        self.min_range_m = float(self.min_range_m)
        self.max_target_speed_mps = float(self.max_target_speed_mps)
        self.ammunition_total = int(self.ammunition_total)
        self.ammunition_remaining = int(self.ammunition_remaining)
        if self.engagement_range_m <= 0:
            raise ValueError("engagement_range_m must be > 0")
        if self.min_range_m < 0:
            raise ValueError("min_range_m must be >= 0")
        if self.min_range_m > self.engagement_range_m:
            raise ValueError("min_range_m cannot exceed engagement_range_m")
        if self.max_target_speed_mps < 0:
            raise ValueError("max_target_speed_mps must be >= 0")
        if self.ammunition_total < 0 or self.ammunition_remaining < 0:
            raise ValueError("ammunition values must be >= 0")
        if self.ammunition_remaining > self.ammunition_total:
            self.ammunition_remaining = self.ammunition_total

    @property
    def is_available(self) -> bool:
        """Whether the unit can be tasked for immediate engagement."""
        return self.state == EffectorState.READY and self.ammunition_remaining > 0

    @property
    def readiness_score(self) -> float:
        """Readiness score used for tactical prioritization."""
        state_weight = {
            EffectorState.READY: 1.0,
            EffectorState.ENGAGING: 0.6,
            EffectorState.RELOADING: 0.3,
            EffectorState.DEGRADED: 0.2,
            EffectorState.OFFLINE: 0.0,
        }[self.state]
        if self.ammunition_total <= 0:
            return 0.0
        ammo_ratio = self.ammunition_remaining / self.ammunition_total
        return max(0.0, min(1.0, state_weight * ammo_ratio))

    def can_engage(self, target_position: tuple, target_speed_mps: float = 0.0) -> bool:
        """Return whether this effector can engage the target kinematically."""
        if not self.is_available:
            return False
        try:
            target_speed = float(target_speed_mps)
        except (TypeError, ValueError):
            return False
        if target_speed < 0 or target_speed > self.max_target_speed_mps:
            return False
        try:
            tx, ty, tz = _normalize_position(target_position)
        except ValueError:
            return False
        ex, ey, ez = self.position
        distance = sqrt((tx - ex) ** 2 + (ty - ey) ** 2 + (tz - ez) ** 2)
        return self.min_range_m <= distance <= self.engagement_range_m
