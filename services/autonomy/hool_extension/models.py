"""Data models for HOOL envelope-bounded autonomous execution.

Military context:
These models define legal and technical guardrails for autonomous operations so
platforms can execute missions without live operator input while staying within
commander-approved boundaries.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple

from src.autonomy.models import AutonomyDecision


class PlatformClass(str, Enum):
    """Supported autonomous platform classes for tactical deployment."""

    UAV_QUADROTOR = "uav_quadrotor"
    UAV_FIXED_WING = "uav_fixed_wing"
    UAV_VTOL = "uav_vtol"
    UGV_WHEELED = "ugv_wheeled"
    UGV_TRACKED = "ugv_tracked"
    USV_SURFACE = "usv_surface"
    UUV_UNDERWATER = "uuv_underwater"


@dataclass
class CompanionCompute:
    """Companion compute profile used for edge deployment planning."""

    platform_class: PlatformClass
    cpu_model: str
    ram_mb: int
    gpu_available: bool
    max_power_watts: float
    os: str
    python_version: str
    ros2_available: bool
    mavlink_available: bool
    llm_capable: bool

    @classmethod
    def for_platform(cls, platform_class: PlatformClass) -> "CompanionCompute":
        """Return canonical companion specification for each platform class."""
        specs: Dict[PlatformClass, Dict[str, Any]] = {
            PlatformClass.UAV_QUADROTOR: {
                "cpu_model": "NVIDIA Jetson Orin Nano 8GB / Raspberry Pi 5",
                "ram_mb": 8192,
                "gpu_available": True,
                "max_power_watts": 25.0,
                "os": "Ubuntu 22.04",
                "python_version": "3.11",
                "ros2_available": True,
                "mavlink_available": True,
                "llm_capable": True,
            },
            PlatformClass.UAV_FIXED_WING: {
                "cpu_model": "NVIDIA Jetson Orin NX 16GB",
                "ram_mb": 16384,
                "gpu_available": True,
                "max_power_watts": 40.0,
                "os": "Ubuntu 22.04",
                "python_version": "3.11",
                "ros2_available": True,
                "mavlink_available": True,
                "llm_capable": True,
            },
            PlatformClass.UAV_VTOL: {
                "cpu_model": "NVIDIA Jetson Orin NX 16GB",
                "ram_mb": 16384,
                "gpu_available": True,
                "max_power_watts": 40.0,
                "os": "Ubuntu 22.04",
                "python_version": "3.11",
                "ros2_available": True,
                "mavlink_available": True,
                "llm_capable": True,
            },
            PlatformClass.UGV_WHEELED: {
                "cpu_model": "NVIDIA Jetson Orin Nano 8GB",
                "ram_mb": 8192,
                "gpu_available": True,
                "max_power_watts": 25.0,
                "os": "Ubuntu 22.04",
                "python_version": "3.11",
                "ros2_available": True,
                "mavlink_available": False,
                "llm_capable": True,
            },
            PlatformClass.UGV_TRACKED: {
                "cpu_model": "NVIDIA Jetson Xavier NX 16GB",
                "ram_mb": 16384,
                "gpu_available": True,
                "max_power_watts": 30.0,
                "os": "Ubuntu 22.04",
                "python_version": "3.11",
                "ros2_available": True,
                "mavlink_available": False,
                "llm_capable": True,
            },
            PlatformClass.USV_SURFACE: {
                "cpu_model": "Raspberry Pi CM4 / Jetson Orin Nano",
                "ram_mb": 4096,
                "gpu_available": False,
                "max_power_watts": 15.0,
                "os": "Ubuntu 22.04",
                "python_version": "3.11",
                "ros2_available": False,
                "mavlink_available": True,
                "llm_capable": False,
            },
            PlatformClass.UUV_UNDERWATER: {
                "cpu_model": "Raspberry Pi 5",
                "ram_mb": 4096,
                "gpu_available": False,
                "max_power_watts": 12.0,
                "os": "Ubuntu 22.04",
                "python_version": "3.11",
                "ros2_available": False,
                "mavlink_available": True,
                "llm_capable": False,
            },
        }
        if platform_class not in specs:
            raise ValueError(f"Unsupported platform class: {platform_class}")
        return cls(platform_class=platform_class, **specs[platform_class])


@dataclass
class MissionEnvelope:
    """Commander-approved autonomy envelope for bounded mission execution."""

    envelope_id: str
    mission_id: str
    approved_by: str
    approved_at: datetime
    geofence_vertices: List[Tuple[float, float, float]]
    geofence_ceiling_m: float
    geofence_floor_m: float
    time_window: Tuple[datetime, datetime]
    roe_level: str
    max_targets: int
    allowed_target_types: List[str]
    min_engagement_confidence: float
    min_battery_pct: float
    min_fuel_pct: float
    max_comms_loss_seconds: float
    max_risk_score: float
    max_escalation_level: int
    custom_constraints: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """Serialize envelope for APIs and signed approval records."""
        return {
            "envelope_id": self.envelope_id,
            "mission_id": self.mission_id,
            "approved_by": self.approved_by,
            "approved_at": self.approved_at.isoformat(),
            "geofence_vertices": [list(v) for v in self.geofence_vertices],
            "geofence_ceiling_m": self.geofence_ceiling_m,
            "geofence_floor_m": self.geofence_floor_m,
            "time_window": [self.time_window[0].isoformat(), self.time_window[1].isoformat()],
            "roe_level": self.roe_level,
            "max_targets": self.max_targets,
            "allowed_target_types": list(self.allowed_target_types),
            "min_engagement_confidence": self.min_engagement_confidence,
            "min_battery_pct": self.min_battery_pct,
            "min_fuel_pct": self.min_fuel_pct,
            "max_comms_loss_seconds": self.max_comms_loss_seconds,
            "max_risk_score": self.max_risk_score,
            "max_escalation_level": self.max_escalation_level,
            "custom_constraints": dict(self.custom_constraints),
        }

    def validate(self) -> tuple[bool, List[str]]:
        """Validate envelope integrity before mission start authorization."""
        issues: List[str] = []
        if not self.envelope_id:
            issues.append("envelope_id is required")
        if len(self.geofence_vertices) < 3:
            issues.append("geofence requires at least 3 vertices")
        for idx, vertex in enumerate(self.geofence_vertices):
            if not isinstance(vertex, tuple) or len(vertex) != 3:
                issues.append(f"geofence vertex {idx} must be (lat, lon, alt)")
        if self.geofence_floor_m >= self.geofence_ceiling_m:
            issues.append("geofence_floor_m must be below geofence_ceiling_m")
        start_dt, end_dt = self.time_window
        if start_dt >= end_dt:
            issues.append("time_window start must be before end")
        if self.roe_level not in {"weapons_free", "weapons_tight", "weapons_hold"}:
            issues.append("roe_level must be weapons_free/weapons_tight/weapons_hold")
        if self.max_targets < 0:
            issues.append("max_targets must be >= 0")
        if not (0.0 <= self.min_engagement_confidence <= 1.0):
            issues.append("min_engagement_confidence must be in [0,1]")
        if not (0.0 <= self.min_battery_pct <= 100.0):
            issues.append("min_battery_pct must be in [0,100]")
        if not (0.0 <= self.min_fuel_pct <= 100.0):
            issues.append("min_fuel_pct must be in [0,100]")
        if self.max_comms_loss_seconds <= 0:
            issues.append("max_comms_loss_seconds must be > 0")
        if not (0.0 <= self.max_risk_score <= 100.0):
            issues.append("max_risk_score must be in [0,100]")
        if not (1 <= self.max_escalation_level <= 5):
            issues.append("max_escalation_level must be between 1 and 5")
        return (len(issues) == 0, issues)


@dataclass
class EnvelopeViolation:
    """One envelope dimension breach used for safety response logic."""

    dimension: str
    current_value: Any
    limit_value: Any
    severity: str
    recoverable: bool
    recommended_action: str


@dataclass
class HOOLDecision(AutonomyDecision):
    """Autonomy decision augmented with envelope and platform metadata."""

    envelope_check: Dict[str, Any] = field(default_factory=dict)
    platform_class: PlatformClass = PlatformClass.UAV_QUADROTOR
    companion_compute: str = "unknown"
    autonomous_level: int = 1

    def to_dict(self) -> Dict[str, Any]:
        data = super().to_dict()
        data.update(
            {
                "envelope_check": dict(self.envelope_check),
                "platform_class": self.platform_class.value,
                "companion_compute": self.companion_compute,
                "autonomous_level": self.autonomous_level,
            }
        )
        return data


@dataclass
class HOOLMissionState:
    """Live HOOL mission state consumed by envelope checks and BT ticks."""

    mission_id: str
    platform_class: PlatformClass
    envelope: MissionEnvelope
    current_position: Tuple[float, float, float]
    battery_pct: float
    comms_status: Any
    targets_engaged: int
    time_remaining_s: float
    risk_score: float
    violations: List[EnvelopeViolation] = field(default_factory=list)
    mode: str = "autonomous"
    fuel_pct: float = 100.0
    proposed_escalation_level: int = 1
    proposed_action: str = "patrol"
    target_type: Optional[str] = None
    target_confidence: float = 0.0
