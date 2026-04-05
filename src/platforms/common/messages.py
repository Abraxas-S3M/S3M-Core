"""Common platform message contracts for S3M-Core HOOL autonomy.

Uses stdlib dataclasses for zero-dependency operation on edge hardware.

UNCLASSIFIED — CLOSED-RANGE TRAINING USE ONLY
"""

from __future__ import annotations

import copy
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple
from uuid import uuid4


# --- Enums ---


class PlatformType(str, Enum):
    UGV = "ugv"
    UAV = "uav"
    USV = "usv"
    FIXED_NODE = "fixed_node"
    PAYLOAD = "payload"


class FaultSeverity(str, Enum):
    INFO = "info"
    WARNING = "warning"
    CRITICAL = "critical"
    FATAL = "fatal"


class ThreatPriority(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class MissionTaskType(str, Enum):
    PATROL = "patrol"
    CONVOY = "convoy"
    ESCORT = "escort"
    PERIMETER_SCAN = "perimeter_scan"
    RTB = "rtb"
    STATION_KEEP = "station_keep"
    LOITER = "loiter"
    INTERCEPT = "intercept"
    ISR = "isr"


class MissionStatus(str, Enum):
    PENDING = "pending"
    ACTIVE = "active"
    PAUSED = "paused"
    COMPLETED = "completed"
    ABORTED = "aborted"
    FAILED = "failed"


class MobilityCommandType(str, Enum):
    GOTO = "goto"
    FOLLOW = "follow"
    HALT = "halt"
    SPEED_SET = "speed_set"
    HEADING_SET = "heading_set"
    FORMATION = "formation"


class SensorCommandType(str, Enum):
    POINT = "point"
    TRACK = "track"
    SCAN = "scan"
    ZOOM = "zoom"
    THERMAL_TOGGLE = "thermal_toggle"
    RECORD = "record"


class AuthorizationType(str, Enum):
    MISSION_START = "mission_start"
    ENGAGE = "engage"
    OVERRIDE = "override"
    SAFE_STATE = "safe_state"
    AUTONOMOUS = "autonomous"


class AuthorityLevel(str, Enum):
    OBSERVER = "observer"
    OPERATOR = "operator"
    WEAPONS_OFFICER = "weapons_officer"
    MISSION_COMMANDER = "mission_commander"


class AutonomyMode(str, Enum):
    HUMAN_IN_THE_LOOP = "human_in_the_loop"
    HUMAN_ON_THE_LOOP = "human_on_the_loop"
    HUMAN_OUT_OF_THE_LOOP = "human_out_of_the_loop"


class InterlockState(str, Enum):
    SAFE = "safe"
    ARMED = "armed"
    FIRING = "firing"
    FAULT = "fault"


class PayloadType(str, Enum):
    RCWS_12_7 = "rcws_12_7"
    RCWS_14_5 = "rcws_14_5"
    SICH_30MM = "sich_30mm"
    ORION_ZU23 = "orion_zu23"
    MANPADS = "manpads"
    ISR_GIMBAL = "isr_gimbal"


# --- Helpers ---


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _uid(prefix: str) -> str:
    return f"{prefix}-{uuid4().hex[:8]}"


# --- Core Messages ---


@dataclass
class FaultEvent:
    severity: FaultSeverity
    source: str
    description: str
    fault_id: str = field(default_factory=lambda: _uid("fault"))
    timestamp: datetime = field(default_factory=_now)
    acknowledged: bool = False

    def to_dict(self) -> Dict[str, Any]:
        return {
            "fault_id": self.fault_id,
            "severity": self.severity.value,
            "source": self.source,
            "description": self.description,
            "timestamp": self.timestamp.isoformat(),
            "acknowledged": self.acknowledged,
        }


@dataclass
class HealthState:
    cpu_temp_c: float = 0.0
    gpu_temp_c: float = 0.0
    memory_pct: float = 0.0
    disk_pct: float = 0.0
    power_voltage: float = 24.0
    operating_mode: str = "full_edge"
    faults: List[FaultEvent] = field(default_factory=list)

    @property
    def has_critical_faults(self) -> bool:
        return any(
            f.severity in {FaultSeverity.CRITICAL, FaultSeverity.FATAL}
            for f in self.faults
        )


@dataclass
class PlatformState:
    platform_id: str
    platform_type: PlatformType
    position: Tuple[float, float, float] = (0.0, 0.0, 0.0)
    heading: float = 0.0
    speed: float = 0.0
    timestamp: datetime = field(default_factory=_now)
    health: HealthState = field(default_factory=HealthState)
    autonomy_level: int = 0
    mission_id: Optional[str] = None
    comms_status: str = "nominal"
    sensors_active: List[str] = field(default_factory=list)
    fuel_pct: float = 100.0
    battery_pct: float = 100.0

    def model_copy(self, update: Optional[Dict[str, Any]] = None) -> "PlatformState":
        new = copy.copy(self)
        for k, v in (update or {}).items():
            setattr(new, k, v)
        return new


@dataclass
class Track:
    track_id: str
    classification: str = "unknown"
    position: Tuple[float, float, float] = (0.0, 0.0, 0.0)
    velocity: Tuple[float, float, float] = (0.0, 0.0, 0.0)
    confidence: float = 0.5
    source_platform_id: str = ""
    sensor_sources: List[str] = field(default_factory=list)
    threat_priority: ThreatPriority = ThreatPriority.LOW
    last_update: datetime = field(default_factory=_now)
    covariance: List[List[float]] = field(
        default_factory=lambda: [[0.0] * 6 for _ in range(6)]
    )

    def __post_init__(self) -> None:
        self.confidence = max(0.0, min(1.0, self.confidence))

    def model_copy(self, update: Optional[Dict[str, Any]] = None) -> "Track":
        new = copy.copy(self)
        for k, v in (update or {}).items():
            setattr(new, k, v)
        return new

    def to_dict(self) -> Dict[str, Any]:
        return {
            "track_id": self.track_id,
            "classification": self.classification,
            "position": self.position,
            "velocity": self.velocity,
            "confidence": self.confidence,
            "threat_priority": self.threat_priority.value,
            "last_update": self.last_update.isoformat(),
        }


@dataclass
class MissionTask:
    task_type: MissionTaskType
    task_id: str = field(default_factory=lambda: _uid("task"))
    waypoints: List[Tuple[float, float, float]] = field(default_factory=list)
    parameters: Dict[str, Any] = field(default_factory=dict)
    priority: int = 1
    assigned_platform: str = ""
    status: MissionStatus = MissionStatus.PENDING

    def model_copy(self, update: Optional[Dict[str, Any]] = None) -> "MissionTask":
        new = copy.copy(self)
        for k, v in (update or {}).items():
            setattr(new, k, v)
        return new


@dataclass
class AutonomyRecommendation:
    source_module: str
    action: str
    confidence: float
    rationale: str
    recommendation_id: str = field(default_factory=lambda: _uid("rec"))
    timestamp: datetime = field(default_factory=_now)
    requires_authorization: bool = True


@dataclass
class OperatorAuthorization:
    operator_id: str
    auth_type: AuthorizationType
    authority_level: AuthorityLevel = AuthorityLevel.OPERATOR
    scope: str = ""
    auth_id: str = field(default_factory=lambda: _uid("auth"))
    timestamp: datetime = field(default_factory=_now)
    expires_at: Optional[datetime] = None
    token: str = field(default_factory=lambda: uuid4().hex)

    @property
    def is_expired(self) -> bool:
        if self.expires_at is None:
            return False
        return datetime.now(timezone.utc) > self.expires_at


@dataclass
class MobilityCommand:
    command_type: MobilityCommandType
    command_id: str = field(default_factory=lambda: _uid("mob"))
    target_position: Optional[Tuple[float, float, float]] = None
    target_speed: Optional[float] = None
    target_heading: Optional[float] = None
    parameters: Dict[str, Any] = field(default_factory=dict)
    timestamp: datetime = field(default_factory=_now)


@dataclass
class SensorCommand:
    command_type: SensorCommandType
    command_id: str = field(default_factory=lambda: _uid("sen"))
    target: Optional[Tuple[float, float, float]] = None
    parameters: Dict[str, Any] = field(default_factory=dict)
    timestamp: datetime = field(default_factory=_now)


@dataclass
class AimSolution:
    target_track_id: str
    solution_id: str = field(default_factory=lambda: _uid("aim"))
    lead_azimuth_deg: float = 0.0
    lead_elevation_deg: float = 0.0
    range_m: float = 0.0
    confidence: float = 0.0
    ballistic_correction: Dict[str, float] = field(default_factory=dict)
    engagement_window_sec: float = 0.0
    timestamp: datetime = field(default_factory=_now)


@dataclass
class PayloadState:
    payload_id: str
    payload_type: PayloadType
    interlock_state: InterlockState = InterlockState.SAFE
    slew_azimuth_deg: float = 0.0
    slew_elevation_deg: float = 0.0
    stabilization_active: bool = False
    ammo_count: int = 0
    ammo_max: int = 0
    barrel_temp_c: float = 20.0
    readiness: str = "not_ready"
    tracking_target_id: Optional[str] = None
    timestamp: datetime = field(default_factory=_now)

    @property
    def ammo_pct(self) -> float:
        return (self.ammo_count / self.ammo_max * 100.0) if self.ammo_max > 0 else 0.0


@dataclass
class EngagementRecommendation:
    target_track: Track
    recommended_effector_id: str
    aim_solution: AimSolution
    recommendation_id: str = field(default_factory=lambda: _uid("eng"))
    autonomy_mode: AutonomyMode = AutonomyMode.HUMAN_IN_THE_LOOP
    confidence: float = 0.0
    roe_compliant: bool = False
    zone_authorized: bool = False
    iff_clear: bool = False
    rationale: str = ""
    engagement_window_sec: float = 0.0
    timestamp: datetime = field(default_factory=_now)

    @property
    def is_auto_authorized(self) -> bool:
        return (
            self.autonomy_mode == AutonomyMode.HUMAN_OUT_OF_THE_LOOP
            and self.confidence >= 0.95
            and self.roe_compliant
            and self.zone_authorized
            and self.iff_clear
        )


@dataclass
class ROEProfile:
    name: str = "default"
    profile_id: str = field(default_factory=lambda: _uid("roe"))
    allowed_target_classifications: List[str] = field(default_factory=list)
    min_confidence: float = 0.8
    max_range_m: float = 5000.0
    min_range_m: float = 50.0
    blue_force_exclusion_radius_m: float = 500.0
    authorization_mode: AutonomyMode = AutonomyMode.HUMAN_IN_THE_LOOP
    active: bool = True
