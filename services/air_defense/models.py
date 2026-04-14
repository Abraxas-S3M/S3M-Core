"""Core models for layered air defense force composition.

Military context:
These models encode a multi-echelon ground-based air defense construct so
simulations can reason about tactical coverage, reaction windows, and
interceptor inventory for critical-asset protection.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Tuple
from uuid import uuid4


class DefenseEchelon(str, Enum):
    """Defensive depth bands used to organize layered engagements."""

    EXTENDED = "extended"
    MEDIUM = "medium"
    SHORT = "short"
    CLOSE = "close"


class EffectorCategory(str, Enum):
    """Operational categories for kinetic and non-kinetic effectors."""

    SAM_MEDIUM = "sam_medium"
    SAM_SHORT = "sam_short"
    CIWS_GUN = "ciws_gun"
    MANPADS = "manpads"
    INTERCEPTOR_DRONE = "interceptor_drone"
    ELECTRONIC_WARFARE = "electronic_warfare"


class EffectorType(str, Enum):
    """Canonical effector system variants represented in S3M templates."""

    BUK_FS = "buk_fs"
    ITEL_SNC = "itel_snc"
    DASH_STASH_V2X = "dash_stash_v2x"
    FRANKEN_SAM = "franken_sam"
    SKYNEX = "skynex"
    SKYRANGER = "skyranger"
    RAPID_RANGER = "rapid_ranger"
    TYPHOON_KDA = "typhoon_kda"
    MANPADS_GENERIC = "manpads_generic"
    INTERCEPTOR_TITAN = "interceptor_titan"
    EW_JAMMER = "ew_jammer"


@dataclass
class EngagementEnvelope:
    """Kinematic and temporal limits that define valid engagement geometry."""

    min_range_m: float
    max_range_m: float
    min_altitude_m: float
    max_altitude_m: float
    max_target_speed_mps: float
    reaction_time_s: float
    engagement_time_s: float
    simultaneous_targets: int
    pk_single_shot: float

    def __post_init__(self) -> None:
        if self.min_range_m < 0 or self.max_range_m < 0:
            raise ValueError("engagement range must be non-negative")
        if self.min_altitude_m < 0 or self.max_altitude_m < 0:
            raise ValueError("engagement altitude must be non-negative")
        if self.max_target_speed_mps <= 0:
            raise ValueError("max_target_speed_mps must be positive")
        if self.reaction_time_s < 0 or self.engagement_time_s < 0:
            raise ValueError("reaction and engagement times must be non-negative")
        if self.min_range_m > self.max_range_m:
            raise ValueError("min_range_m cannot exceed max_range_m")
        if self.min_altitude_m > self.max_altitude_m:
            raise ValueError("min_altitude_m cannot exceed max_altitude_m")
        if self.simultaneous_targets < 1:
            raise ValueError("simultaneous_targets must be at least 1")
        if not 0.0 <= self.pk_single_shot <= 1.0:
            raise ValueError("pk_single_shot must be between 0 and 1")


@dataclass
class Effector:
    """Single tactical effector node with inventory and engagement limits."""

    name_en: str
    name_ar: str
    effector_type: EffectorType
    category: EffectorCategory
    echelon: DefenseEchelon
    envelope: EngagementEnvelope
    position: Tuple[float, float, float]
    ammunition_total: int
    ammunition_remaining: int
    reload_time_s: float
    assigned_zone_id: str
    effector_id: str = field(default_factory=lambda: f"eff-{uuid4().hex[:12]}")

    def __post_init__(self) -> None:
        if not self.name_en.strip() or not self.name_ar.strip():
            raise ValueError("effector names must be non-empty")
        if len(self.position) != 3:
            raise ValueError("position must be a 3D coordinate tuple")
        if self.ammunition_total < 0:
            raise ValueError("ammunition_total must be non-negative")
        if self.ammunition_remaining < 0:
            raise ValueError("ammunition_remaining must be non-negative")
        if self.ammunition_remaining > self.ammunition_total:
            raise ValueError("ammunition_remaining cannot exceed ammunition_total")
        if self.reload_time_s < 0:
            raise ValueError("reload_time_s must be non-negative")
        if not self.assigned_zone_id.strip():
            raise ValueError("assigned_zone_id must be non-empty")


@dataclass
class DefenseZone:
    """Radial defense zone that groups effectors by tactical echelon."""

    zone_id: str
    echelon: DefenseEchelon
    center: Tuple[float, float, float]
    radius_min_m: float
    radius_max_m: float
    defended_asset_name: str
    defended_asset_name_ar: str
    assigned_effector_ids: list[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        if len(self.center) != 3:
            raise ValueError("zone center must be a 3D coordinate tuple")
        if self.radius_min_m < 0 or self.radius_max_m < 0:
            raise ValueError("zone radii must be non-negative")
        if self.radius_min_m > self.radius_max_m:
            raise ValueError("radius_min_m cannot exceed radius_max_m")
        if not self.zone_id.strip():
            raise ValueError("zone_id must be non-empty")


@dataclass
class AirDefenseUnit:
    """Air defense order of battle anchored to a defended asset."""

    name_en: str
    name_ar: str
    defended_asset: str
    position: Tuple[float, float, float]
    effector_ids: list[str]
    zone_ids: list[str]
    unit_id: str = field(default_factory=lambda: f"adu-{uuid4().hex[:12]}")

    def __post_init__(self) -> None:
        if not self.name_en.strip() or not self.name_ar.strip():
            raise ValueError("unit names must be non-empty")
        if len(self.position) != 3:
            raise ValueError("unit position must be a 3D coordinate tuple")
        if not self.effector_ids:
            raise ValueError("air defense unit must include at least one effector")
        if not self.zone_ids:
            raise ValueError("air defense unit must include at least one defense zone")
