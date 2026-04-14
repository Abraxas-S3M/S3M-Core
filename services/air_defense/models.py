"""Typed air-defense data models for registry, zones, and allocations.

Military context:
These dataclasses formalize effector readiness, engagement envelopes, and
layered defense geometry so tactical command nodes can make deterministic,
auditable fire-control choices during disconnected operations.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
import math
import time
from typing import Any, Dict, List, Optional, Tuple


def _require_non_empty(value: str, field_name: str) -> str:
    text = str(value).strip()
    if not text:
        raise ValueError(f"{field_name} must be non-empty")
    return text


def _validate_finite(value: float, field_name: str) -> float:
    number = float(value)
    if not math.isfinite(number):
        raise ValueError(f"{field_name} must be finite")
    return number


def _normalize_degrees(angle_deg: float) -> float:
    normalized = float(angle_deg) % 360.0
    if normalized < 0:
        normalized += 360.0
    return normalized


class EffectorType(str, Enum):
    """Known air-defense effector archetypes used by S3M registries."""

    PATRIOT_PAC3 = "patriot_pac3"
    THAAD = "thaad"
    HAWK_XXI = "hawk_xxi"
    NASAMS_AMRAAM = "nasams_amraam"
    SAMP_T = "samp_t"
    SKY_DRAGON = "sky_dragon"
    SPYDER_SR = "spyder_sr"
    SHAHINE = "shahine"
    CROTAL_NG = "crotal_ng"
    PANTSIR_S1 = "pantsir_s1"
    AVENGER = "avenger"
    IRIS_T_SLS = "iris_t_sls"
    SKYGUARD_35MM = "skyguard_35mm"
    OERLIKON_GDF005 = "oerlikon_gdf005"
    ZSU_23_4 = "zsu_23_4"
    MISTRAL_MANPADS = "mistral_manpads"
    STINGER_MANPADS = "stinger_manpads"
    QW18_MANPADS = "qw18_manpads"
    SHORAD_LASER = "shorad_laser"
    ELECTRONIC_KILL = "electronic_kill"


class EffectorCategory(str, Enum):
    """Effector class used for allocation and fallback policies."""

    MISSILE = "missile"
    GUN = "gun"
    MANPADS = "manpads"
    DIRECTED_ENERGY = "directed_energy"
    ELECTRONIC_WARFARE = "electronic_warfare"


class DefenseEchelon(str, Enum):
    """Layered defense echelons from outer to inner ring."""

    MEDIUM = "medium"
    SHORT = "short"
    CLOSE = "close"


@dataclass
class EngagementEnvelope:
    """Geometric engagement envelope relative to an effector position."""

    min_range_km: float
    max_range_km: float
    min_altitude_m: float
    max_altitude_m: float
    azimuth_start_deg: float = 0.0
    azimuth_end_deg: float = 360.0

    def __post_init__(self) -> None:
        self.min_range_km = _validate_finite(self.min_range_km, "min_range_km")
        self.max_range_km = _validate_finite(self.max_range_km, "max_range_km")
        self.min_altitude_m = _validate_finite(self.min_altitude_m, "min_altitude_m")
        self.max_altitude_m = _validate_finite(self.max_altitude_m, "max_altitude_m")
        self.azimuth_start_deg = _normalize_degrees(_validate_finite(self.azimuth_start_deg, "azimuth_start_deg"))
        self.azimuth_end_deg = _normalize_degrees(_validate_finite(self.azimuth_end_deg, "azimuth_end_deg"))

        if self.min_range_km < 0.0:
            raise ValueError("min_range_km must be >= 0")
        if self.max_range_km <= self.min_range_km:
            raise ValueError("max_range_km must be greater than min_range_km")
        if self.min_altitude_m < 0.0:
            raise ValueError("min_altitude_m must be >= 0")
        if self.max_altitude_m <= self.min_altitude_m:
            raise ValueError("max_altitude_m must be greater than min_altitude_m")

    def is_full_azimuth(self) -> bool:
        """Return True when envelope provides full 360-degree coverage."""
        span = (self.azimuth_end_deg - self.azimuth_start_deg) % 360.0
        return math.isclose(span, 0.0, abs_tol=1e-6)

    def azimuth_span_deg(self) -> float:
        """Return azimuth span in degrees, mapping full circle to 360."""
        span = (self.azimuth_end_deg - self.azimuth_start_deg) % 360.0
        return 360.0 if math.isclose(span, 0.0, abs_tol=1e-6) else span

    def covers_range(self, range_km: float) -> bool:
        """Check horizontal range eligibility."""
        distance = _validate_finite(range_km, "range_km")
        return self.min_range_km <= distance <= self.max_range_km

    def covers_altitude(self, altitude_m: float) -> bool:
        """Check altitude eligibility."""
        altitude = _validate_finite(altitude_m, "altitude_m")
        return self.min_altitude_m <= altitude <= self.max_altitude_m

    def covers_azimuth(self, azimuth_deg: float) -> bool:
        """Check azimuth eligibility, supporting wrap-around sectors."""
        if self.is_full_azimuth():
            return True
        azimuth = _normalize_degrees(_validate_finite(azimuth_deg, "azimuth_deg"))
        if self.azimuth_start_deg <= self.azimuth_end_deg:
            return self.azimuth_start_deg <= azimuth <= self.azimuth_end_deg
        return azimuth >= self.azimuth_start_deg or azimuth <= self.azimuth_end_deg

    def azimuth_coverage_ratio(self) -> float:
        """Return fraction of 360-degree coverage represented by the envelope."""
        return self.azimuth_span_deg() / 360.0


@dataclass
class EffectorState:
    """Mutable readiness and ammunition state for one effector channel."""

    readiness: float
    ammunition_current: int
    ammunition_capacity: int
    reload_time_seconds: float
    status: str = "ready"
    last_fired_timestamp: Optional[float] = None
    queued_targets: int = 0

    def __post_init__(self) -> None:
        self.readiness = _validate_finite(self.readiness, "readiness")
        self.reload_time_seconds = _validate_finite(self.reload_time_seconds, "reload_time_seconds")
        self.ammunition_current = int(self.ammunition_current)
        self.ammunition_capacity = int(self.ammunition_capacity)
        self.queued_targets = int(self.queued_targets)
        self.status = _require_non_empty(self.status, "status").lower()

        if not 0.0 <= self.readiness <= 1.0:
            raise ValueError("readiness must be in [0.0, 1.0]")
        if self.ammunition_capacity < 0:
            raise ValueError("ammunition_capacity must be >= 0")
        if not 0 <= self.ammunition_current <= self.ammunition_capacity:
            raise ValueError("ammunition_current must be within [0, ammunition_capacity]")
        if self.reload_time_seconds < 0.0:
            raise ValueError("reload_time_seconds must be >= 0")
        if self.queued_targets < 0:
            raise ValueError("queued_targets must be >= 0")
        if self.last_fired_timestamp is not None:
            self.last_fired_timestamp = _validate_finite(self.last_fired_timestamp, "last_fired_timestamp")
        if self.status not in {"ready", "degraded", "reloading", "offline", "maintenance"}:
            raise ValueError("status must be one of ready/degraded/reloading/offline/maintenance")

    def has_ammunition(self, rounds_required: int = 1) -> bool:
        """Return True when enough ammunition is present for a shot."""
        required = max(1, int(rounds_required))
        return self.ammunition_current >= required

    def reload_complete(self, now_ts: Optional[float] = None) -> bool:
        """Return True if temporal reload constraints are satisfied."""
        now = time.time() if now_ts is None else _validate_finite(now_ts, "now_ts")
        if self.last_fired_timestamp is None:
            return True
        elapsed = now - self.last_fired_timestamp
        return elapsed >= self.reload_time_seconds

    def is_ready(self, now_ts: Optional[float] = None, rounds_required: int = 1) -> bool:
        """Readiness gate used by allocators and engagement planners."""
        if self.status not in {"ready", "degraded"}:
            return False
        if self.readiness < 0.5:
            return False
        if not self.has_ammunition(rounds_required=rounds_required):
            return False
        return self.reload_complete(now_ts=now_ts)


@dataclass
class Effector:
    """Registered air-defense effector and current tactical capability."""

    effector_id: str
    name_en: str
    name_ar: str
    effector_type: EffectorType
    category: EffectorCategory
    echelon: DefenseEchelon
    envelope: EngagementEnvelope
    state: EffectorState
    zone_id: str
    position: Tuple[float, float, float]
    priority: int = 100
    metadata: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        self.effector_id = _require_non_empty(self.effector_id, "effector_id")
        self.name_en = _require_non_empty(self.name_en, "name_en")
        self.name_ar = _require_non_empty(self.name_ar, "name_ar")
        self.zone_id = _require_non_empty(self.zone_id, "zone_id")
        self.priority = int(self.priority)

        if self.priority < 0:
            raise ValueError("priority must be >= 0")
        if len(self.position) != 3:
            raise ValueError("position must have three coordinates (x, y, z)")
        self.position = (
            _validate_finite(self.position[0], "position_x"),
            _validate_finite(self.position[1], "position_y"),
            _validate_finite(self.position[2], "position_z"),
        )

    def ground_range_km_to(self, target_position: Tuple[float, float, float]) -> float:
        """Return ground range in km from effector to target."""
        if len(target_position) != 3:
            raise ValueError("target_position must have three coordinates")
        dx = _validate_finite(target_position[0], "target_x") - self.position[0]
        dy = _validate_finite(target_position[1], "target_y") - self.position[1]
        return math.hypot(dx, dy)

    def azimuth_to(self, target_position: Tuple[float, float, float]) -> float:
        """Return azimuth in degrees from effector to target."""
        if len(target_position) != 3:
            raise ValueError("target_position must have three coordinates")
        dx = _validate_finite(target_position[0], "target_x") - self.position[0]
        dy = _validate_finite(target_position[1], "target_y") - self.position[1]
        return _normalize_degrees(math.degrees(math.atan2(dy, dx)))

    def can_engage(self, target_position: Tuple[float, float, float], now_ts: Optional[float] = None) -> bool:
        """Return True if state and geometry permit engagement."""
        range_km = self.ground_range_km_to(target_position)
        azimuth = self.azimuth_to(target_position)
        altitude = _validate_finite(target_position[2], "target_altitude_m")
        return (
            self.state.is_ready(now_ts=now_ts)
            and self.envelope.covers_range(range_km)
            and self.envelope.covers_altitude(altitude)
            and self.envelope.covers_azimuth(azimuth)
        )


@dataclass
class DefenseZone:
    """Layered defense zone represented as a ring sector around a center."""

    zone_id: str
    name_en: str
    name_ar: str
    echelon: DefenseEchelon
    center: Tuple[float, float]
    radius_km: float
    min_radius_km: float = 0.0
    min_altitude_m: float = 0.0
    max_altitude_m: float = 50000.0
    azimuth_start_deg: float = 0.0
    azimuth_end_deg: float = 360.0
    unit_id: str = ""

    def __post_init__(self) -> None:
        self.zone_id = _require_non_empty(self.zone_id, "zone_id")
        self.name_en = _require_non_empty(self.name_en, "name_en")
        self.name_ar = _require_non_empty(self.name_ar, "name_ar")
        if self.unit_id:
            self.unit_id = _require_non_empty(self.unit_id, "unit_id")

        if len(self.center) != 2:
            raise ValueError("center must include two coordinates (x, y)")
        self.center = (
            _validate_finite(self.center[0], "center_x"),
            _validate_finite(self.center[1], "center_y"),
        )
        self.radius_km = _validate_finite(self.radius_km, "radius_km")
        self.min_radius_km = _validate_finite(self.min_radius_km, "min_radius_km")
        self.min_altitude_m = _validate_finite(self.min_altitude_m, "min_altitude_m")
        self.max_altitude_m = _validate_finite(self.max_altitude_m, "max_altitude_m")
        self.azimuth_start_deg = _normalize_degrees(_validate_finite(self.azimuth_start_deg, "azimuth_start_deg"))
        self.azimuth_end_deg = _normalize_degrees(_validate_finite(self.azimuth_end_deg, "azimuth_end_deg"))

        if self.min_radius_km < 0.0:
            raise ValueError("min_radius_km must be >= 0")
        if self.radius_km <= self.min_radius_km:
            raise ValueError("radius_km must be greater than min_radius_km")
        if self.min_altitude_m < 0.0:
            raise ValueError("min_altitude_m must be >= 0")
        if self.max_altitude_m <= self.min_altitude_m:
            raise ValueError("max_altitude_m must be greater than min_altitude_m")

    def azimuth_span_deg(self) -> float:
        """Return sector azimuth span in degrees."""
        span = (self.azimuth_end_deg - self.azimuth_start_deg) % 360.0
        return 360.0 if math.isclose(span, 0.0, abs_tol=1e-6) else span

    def coverage_ratio(self) -> float:
        """Return percentage of full-circle horizontal coverage."""
        return self.azimuth_span_deg() / 360.0

    def area_km2(self) -> float:
        """Return horizontal area in square kilometers."""
        ring_area = math.pi * (self.radius_km**2 - self.min_radius_km**2)
        return ring_area * self.coverage_ratio()

    def _covers_azimuth(self, azimuth_deg: float) -> bool:
        if math.isclose(self.azimuth_span_deg(), 360.0, abs_tol=1e-6):
            return True
        angle = _normalize_degrees(azimuth_deg)
        if self.azimuth_start_deg <= self.azimuth_end_deg:
            return self.azimuth_start_deg <= angle <= self.azimuth_end_deg
        return angle >= self.azimuth_start_deg or angle <= self.azimuth_end_deg

    def distance_km_to(self, x_km: float, y_km: float) -> float:
        """Return horizontal distance from zone center to point."""
        dx = _validate_finite(x_km, "x_km") - self.center[0]
        dy = _validate_finite(y_km, "y_km") - self.center[1]
        return math.hypot(dx, dy)

    def contains_point(self, x_km: float, y_km: float, altitude_m: float) -> bool:
        """Return True if 3D point is inside this defense zone."""
        altitude = _validate_finite(altitude_m, "altitude_m")
        if not self.min_altitude_m <= altitude <= self.max_altitude_m:
            return False
        distance = self.distance_km_to(x_km=x_km, y_km=y_km)
        if not self.min_radius_km <= distance <= self.radius_km:
            return False
        azimuth = _normalize_degrees(math.degrees(math.atan2(y_km - self.center[1], x_km - self.center[0])))
        return self._covers_azimuth(azimuth)


@dataclass
class AirDefenseUnit:
    """Aggregate command object for zones and effectors under one unit."""

    unit_id: str
    name_en: str
    name_ar: str
    effectors: List[Effector] = field(default_factory=list)
    zones: List[DefenseZone] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        self.unit_id = _require_non_empty(self.unit_id, "unit_id")
        self.name_en = _require_non_empty(self.name_en, "name_en")
        self.name_ar = _require_non_empty(self.name_ar, "name_ar")

        effector_ids = [e.effector_id for e in self.effectors]
        if len(set(effector_ids)) != len(effector_ids):
            raise ValueError("effectors must have unique effector_id values")
        zone_ids = [z.zone_id for z in self.zones]
        if len(set(zone_ids)) != len(zone_ids):
            raise ValueError("zones must have unique zone_id values")


@dataclass
class TargetAllocation:
    """Allocation decision mapping one target to one effector."""

    allocation_id: str
    target_id: str
    target_type: str
    target_position: Tuple[float, float, float]
    assigned_effector_id: str
    echelon: DefenseEchelon
    score: float
    reason: str
    queued_index: int
    created_at: float = field(default_factory=time.time)
    fallback_depth: int = 0

    def __post_init__(self) -> None:
        self.allocation_id = _require_non_empty(self.allocation_id, "allocation_id")
        self.target_id = _require_non_empty(self.target_id, "target_id")
        self.target_type = _require_non_empty(self.target_type, "target_type")
        self.assigned_effector_id = _require_non_empty(self.assigned_effector_id, "assigned_effector_id")
        self.score = _validate_finite(self.score, "score")
        self.queued_index = int(self.queued_index)
        self.fallback_depth = int(self.fallback_depth)
        self.created_at = _validate_finite(self.created_at, "created_at")
        if len(self.target_position) != 3:
            raise ValueError("target_position must have three coordinates")
        self.target_position = (
            _validate_finite(self.target_position[0], "target_x"),
            _validate_finite(self.target_position[1], "target_y"),
            _validate_finite(self.target_position[2], "target_z"),
        )
        if not 0.0 <= self.score <= 100.0:
            raise ValueError("score must be in [0.0, 100.0]")
        if self.queued_index < 0:
            raise ValueError("queued_index must be >= 0")
        if self.fallback_depth < 0:
            raise ValueError("fallback_depth must be >= 0")


@dataclass
class AllocationResult:
    """Allocator output with chosen effector and rejected candidates."""

    target_id: str
    selected_allocation: Optional[TargetAllocation]
    considered_allocations: List[TargetAllocation] = field(default_factory=list)
    unavailable_reasons: Dict[str, str] = field(default_factory=dict)
    queue_depth_by_effector: Dict[str, int] = field(default_factory=dict)
    fallback_required: bool = False

    def __post_init__(self) -> None:
        self.target_id = _require_non_empty(self.target_id, "target_id")
        self.fallback_required = bool(self.fallback_required)
        if self.selected_allocation and self.selected_allocation.target_id != self.target_id:
            raise ValueError("selected_allocation target_id must match AllocationResult target_id")
        for allocation in self.considered_allocations:
            if allocation.target_id != self.target_id:
                raise ValueError("considered allocation target_id mismatch")

    @property
    def allocated(self) -> bool:
        """Return True if a valid effector assignment exists."""
        return self.selected_allocation is not None
