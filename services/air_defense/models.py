"""Core data models for S3M air defense effector management.

Military context:
These models represent the typed effector taxonomy, engagement envelopes,
and echeloned defense zones required for Krechet-equivalent C2 operations.
Every effector carries its physical engagement constraints so the allocator
can make geometry-aware fire distribution decisions.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from math import atan2, degrees, sqrt
from typing import Any, Dict, List, Optional, Tuple
from uuid import uuid4


class EffectorType(str, Enum):
    """Typed effector taxonomy matching Krechet 9C905 integration catalog."""

    # Medium-range SAM systems (20-40km)
    IRIS_T_SLM = "iris_t_slm"
    BUK_M1 = "buk_m1"
    BUK_FS = "buk_fs"

    # Short-range SAM systems (5-20km)
    ITEL_SNC = "itel_snc"
    DASH_STASH_V2X = "dash_stash_v2x"
    FRANKEN_SAM = "franken_sam"

    # Close-range gun/missile systems (0.5-10km)
    SKYNEX = "skynex"
    SKYRANGER = "skyranger"
    RAPID_RANGER = "rapid_ranger"
    TYPHOON_KDA = "typhoon_kda"
    KDV_DIHL = "kdv_dihl"

    # MANPADS (0.5-6km)
    MANPADS_IGLA = "manpads_igla"
    MANPADS_STINGER = "manpads_stinger"
    MANPADS_GENERIC = "manpads_generic"

    # Interceptor drones (5-40km)
    INTERCEPTOR_TITAN = "interceptor_titan"
    INTERCEPTOR_GENERIC = "interceptor_generic"

    # Electronic warfare
    EW_JAMMER = "ew_jammer"
    EW_SPOOFER = "ew_spoofer"

    # Generic / user-defined
    CUSTOM = "custom"


class EffectorCategory(str, Enum):
    """High-level effector family for echelon assignment."""

    SAM_MEDIUM = "sam_medium"
    SAM_SHORT = "sam_short"
    CIWS_GUN = "ciws_gun"
    MANPADS = "manpads"
    INTERCEPTOR_DRONE = "interceptor_drone"
    ELECTRONIC_WARFARE = "electronic_warfare"


class DefenseEchelon(str, Enum):
    """Layered defense echelon matching Krechet coverage concept."""

    CLOSE = "close"  # 0 - 10 km
    SHORT = "short"  # 10 - 20 km
    MEDIUM = "medium"  # 20 - 40 km
    EXTENDED = "extended"  # 40+ km (interceptor drone outer envelope)


class EffectorState(str, Enum):
    """Operational readiness state of a single effector unit."""

    READY = "ready"
    ENGAGING = "engaging"
    RELOADING = "reloading"
    DEGRADED = "degraded"
    OFFLINE = "offline"
    DESTROYED = "destroyed"


@dataclass
class EngagementEnvelope:
    """Physical engagement constraints for an effector type.

    Military context:
    Defines the 3D volume where this effector can effectively engage targets.
    The allocator uses these bounds to determine geometric feasibility before
    assigning a target to this effector.
    """

    min_range_m: float
    max_range_m: float
    min_altitude_m: float
    max_altitude_m: float
    min_azimuth_deg: float = 0.0  # 0 = full 360 coverage
    max_azimuth_deg: float = 360.0
    max_target_speed_mps: float = 500.0
    reaction_time_s: float = 5.0
    engagement_time_s: float = 10.0
    simultaneous_targets: int = 1
    pk_single_shot: float = 0.7  # probability of kill per shot

    def __post_init__(self) -> None:
        if self.min_range_m < 0 or self.max_range_m <= self.min_range_m:
            raise ValueError("Invalid range bounds")
        if self.min_altitude_m < 0 or self.max_altitude_m < self.min_altitude_m:
            raise ValueError("Invalid altitude bounds")
        if not (0.0 <= self.pk_single_shot <= 1.0):
            raise ValueError("pk_single_shot must be in [0, 1]")

    def target_in_envelope(
        self,
        target_range_m: float,
        target_altitude_m: float,
        target_speed_mps: float = 0.0,
        target_azimuth_deg: float = 0.0,
    ) -> bool:
        """Return True if target is within this effector's engagement envelope."""
        if not (self.min_range_m <= target_range_m <= self.max_range_m):
            return False
        if not (self.min_altitude_m <= target_altitude_m <= self.max_altitude_m):
            return False
        if target_speed_mps > self.max_target_speed_mps:
            return False
        if self.min_azimuth_deg != 0.0 or self.max_azimuth_deg != 360.0:
            az = target_azimuth_deg % 360.0
            if self.min_azimuth_deg <= self.max_azimuth_deg:
                if not (self.min_azimuth_deg <= az <= self.max_azimuth_deg):
                    return False
            else:  # wraps around 0
                if not (az >= self.min_azimuth_deg or az <= self.max_azimuth_deg):
                    return False
        return True


@dataclass
class Effector:
    """Single air defense effector unit with full state tracking.

    Military context:
    Represents one launcher, gun system, interceptor drone station, MANPADS team,
    or EW jammer - the atomic unit the C2 system commands. Each carries its own
    position, ammunition state, and engagement envelope.
    """

    effector_id: str = field(default_factory=lambda: f"eff-{uuid4().hex[:10]}")
    name_en: str = ""
    name_ar: str = ""
    effector_type: EffectorType = EffectorType.CUSTOM
    category: EffectorCategory = EffectorCategory.CIWS_GUN
    echelon: DefenseEchelon = DefenseEchelon.CLOSE
    envelope: EngagementEnvelope = field(
        default_factory=lambda: EngagementEnvelope(
            min_range_m=500, max_range_m=5000, min_altitude_m=10, max_altitude_m=3000
        )
    )
    position: Tuple[float, float, float] = (0.0, 0.0, 0.0)
    heading_deg: float = 0.0
    state: EffectorState = EffectorState.READY
    ammunition_total: int = 0
    ammunition_remaining: int = 0
    reload_time_s: float = 30.0
    current_target_id: Optional[str] = None
    engagement_start: Optional[datetime] = None
    engagements_completed: int = 0
    kills_confirmed: int = 0
    assigned_zone_id: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not isinstance(self.effector_id, str) or not self.effector_id.strip():
            raise ValueError("effector_id must be a non-empty string")
        if not isinstance(self.effector_type, EffectorType):
            self.effector_type = EffectorType(self.effector_type)
        if not isinstance(self.category, EffectorCategory):
            self.category = EffectorCategory(self.category)
        if not isinstance(self.echelon, DefenseEchelon):
            self.echelon = DefenseEchelon(self.echelon)
        if not isinstance(self.state, EffectorState):
            self.state = EffectorState(self.state)

    @property
    def is_available(self) -> bool:
        """True if effector can accept a new target assignment."""
        return (
            self.state == EffectorState.READY
            and self.ammunition_remaining > 0
            and self.current_target_id is None
        )

    @property
    def readiness_score(self) -> float:
        """0.0-1.0 composite readiness considering ammo, state, engagement load."""
        if self.state in {EffectorState.OFFLINE, EffectorState.DESTROYED}:
            return 0.0
        base = 0.5 if self.state == EffectorState.DEGRADED else 1.0
        ammo_ratio = self.ammunition_remaining / max(1, self.ammunition_total)
        busy_penalty = 0.3 if self.current_target_id else 0.0
        return max(0.0, min(1.0, base * ammo_ratio - busy_penalty))

    def range_to(self, target_position: Tuple[float, float, float]) -> float:
        """Slant range from effector to target in meters."""
        dx = target_position[0] - self.position[0]
        dy = target_position[1] - self.position[1]
        dz = target_position[2] - self.position[2]
        return sqrt(dx * dx + dy * dy + dz * dz)

    def azimuth_to(self, target_position: Tuple[float, float, float]) -> float:
        """Azimuth bearing from effector to target in degrees (0=North, CW)."""
        dx = target_position[0] - self.position[0]
        dy = target_position[1] - self.position[1]
        return degrees(atan2(dx, dy)) % 360.0

    def can_engage(
        self,
        target_position: Tuple[float, float, float],
        target_speed_mps: float = 0.0,
    ) -> bool:
        """Full engagement feasibility check: state + envelope + ammo."""
        if not self.is_available:
            return False
        slant_range = self.range_to(target_position)
        altitude = target_position[2]
        azimuth = self.azimuth_to(target_position)
        return self.envelope.target_in_envelope(
            slant_range, altitude, target_speed_mps, azimuth
        )

    def begin_engagement(self, target_id: str) -> None:
        """Transition to engaging state."""
        self.state = EffectorState.ENGAGING
        self.current_target_id = target_id
        self.engagement_start = datetime.now(timezone.utc)

    def complete_engagement(self, kill: bool = False) -> None:
        """Complete engagement cycle, update ammo, transition state."""
        self.engagements_completed += 1
        self.ammunition_remaining = max(0, self.ammunition_remaining - 1)
        if kill:
            self.kills_confirmed += 1
        self.current_target_id = None
        self.engagement_start = None
        if self.ammunition_remaining <= 0:
            self.state = EffectorState.RELOADING
        else:
            self.state = EffectorState.READY

    def to_dict(self) -> Dict[str, Any]:
        """Serialize for API responses and audit logs."""
        return {
            "effector_id": self.effector_id,
            "name_en": self.name_en,
            "name_ar": self.name_ar,
            "effector_type": self.effector_type.value,
            "category": self.category.value,
            "echelon": self.echelon.value,
            "state": self.state.value,
            "position": list(self.position),
            "ammunition_remaining": self.ammunition_remaining,
            "ammunition_total": self.ammunition_total,
            "readiness_score": round(self.readiness_score, 3),
            "is_available": self.is_available,
            "current_target_id": self.current_target_id,
            "assigned_zone_id": self.assigned_zone_id,
            "engagements_completed": self.engagements_completed,
            "kills_confirmed": self.kills_confirmed,
        }


@dataclass
class DefenseZone:
    """Spatial defense zone representing one echelon layer.

    Military context:
    Maps to the Krechet layered coverage concept: close (1.5-10km),
    short (10-20km), medium (20-40km). Each zone is a circular sector
    centered on the defended asset with assigned effectors.
    """

    zone_id: str = field(default_factory=lambda: f"zone-{uuid4().hex[:8]}")
    name_en: str = ""
    name_ar: str = ""
    echelon: DefenseEchelon = DefenseEchelon.CLOSE
    center: Tuple[float, float, float] = (0.0, 0.0, 0.0)
    inner_radius_m: float = 0.0
    outer_radius_m: float = 10000.0
    min_altitude_m: float = 0.0
    max_altitude_m: float = 5000.0
    min_azimuth_deg: float = 0.0
    max_azimuth_deg: float = 360.0
    assigned_effector_ids: List[str] = field(default_factory=list)
    priority: int = 1  # lower = higher priority
    active: bool = True

    def __post_init__(self) -> None:
        if self.inner_radius_m < 0 or self.outer_radius_m <= self.inner_radius_m:
            raise ValueError("Invalid radius bounds for defense zone")

    def contains_point(self, point: Tuple[float, float, float]) -> bool:
        """Check if a 3D point falls within this zone's volume."""
        dx = point[0] - self.center[0]
        dy = point[1] - self.center[1]
        ground_range = sqrt(dx * dx + dy * dy)
        altitude = point[2]
        if not (self.inner_radius_m <= ground_range <= self.outer_radius_m):
            return False
        if not (self.min_altitude_m <= altitude <= self.max_altitude_m):
            return False
        if self.min_azimuth_deg == 0.0 and self.max_azimuth_deg == 360.0:
            return True
        azimuth = degrees(atan2(dx, dy)) % 360.0
        if self.min_azimuth_deg <= self.max_azimuth_deg:
            return self.min_azimuth_deg <= azimuth <= self.max_azimuth_deg
        return azimuth >= self.min_azimuth_deg or azimuth <= self.max_azimuth_deg

    def to_dict(self) -> Dict[str, Any]:
        return {
            "zone_id": self.zone_id,
            "name_en": self.name_en,
            "name_ar": self.name_ar,
            "echelon": self.echelon.value,
            "center": list(self.center),
            "inner_radius_m": self.inner_radius_m,
            "outer_radius_m": self.outer_radius_m,
            "altitude_range": [self.min_altitude_m, self.max_altitude_m],
            "assigned_effectors": len(self.assigned_effector_ids),
            "active": self.active,
            "priority": self.priority,
        }


@dataclass
class AirDefenseUnit:
    """Composite air defense unit grouping effectors and zones.

    Military context:
    Represents a Krechet-equivalent C2 node with its subordinate effectors
    organized into defense zones. One AirDefenseUnit = one 9C905 system.
    """

    unit_id: str = field(default_factory=lambda: f"adu-{uuid4().hex[:8]}")
    name_en: str = "Air Defense Unit"
    name_ar: str = "وحدة دفاع جوي"
    defended_asset: str = ""
    position: Tuple[float, float, float] = (0.0, 0.0, 0.0)
    effector_ids: List[str] = field(default_factory=list)
    zone_ids: List[str] = field(default_factory=list)
    operational: bool = True


@dataclass
class TargetAllocation:
    """Single target-to-effector assignment decision.

    Military context:
    Records which effector was assigned to which target, why it was chosen,
    and the computed engagement parameters. Used for audit trail and
    miss-handler re-allocation.
    """

    allocation_id: str = field(default_factory=lambda: f"alloc-{uuid4().hex[:10]}")
    target_id: str = ""
    target_position: Tuple[float, float, float] = (0.0, 0.0, 0.0)
    target_speed_mps: float = 0.0
    target_classification: str = ""
    effector_id: str = ""
    effector_type: EffectorType = EffectorType.CUSTOM
    echelon: DefenseEchelon = DefenseEchelon.CLOSE
    zone_id: str = ""
    slant_range_m: float = 0.0
    pk_estimate: float = 0.0
    suitability_score: float = 0.0
    reasoning: str = ""
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    status: str = "pending"  # pending | engaging | hit | miss | aborted
    attempts: int = 0
    max_attempts: int = 3
    fallback_effector_ids: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "allocation_id": self.allocation_id,
            "target_id": self.target_id,
            "effector_id": self.effector_id,
            "effector_type": self.effector_type.value,
            "echelon": self.echelon.value,
            "slant_range_m": round(self.slant_range_m, 1),
            "pk_estimate": round(self.pk_estimate, 3),
            "suitability_score": round(self.suitability_score, 3),
            "reasoning": self.reasoning,
            "status": self.status,
            "attempts": self.attempts,
        }


@dataclass
class AllocationResult:
    """Result of a target allocation request across the defense system."""

    allocated: bool = False
    allocation: Optional[TargetAllocation] = None
    alternatives_count: int = 0
    reasoning: str = ""
    echelon_used: Optional[DefenseEchelon] = None
