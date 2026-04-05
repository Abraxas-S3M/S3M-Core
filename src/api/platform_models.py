"""Pydantic v2 models for tactical platform adapter API routes.

These schemas mirror shared dataclasses used by platform and payload adapters
so operator commands and telemetry remain consistent across battlefield domains.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from src.platforms.common.messages import (
    AuthorizationType,
    AutonomyMode,
    AuthorityLevel,
    HealthState,
    InterlockState,
    MissionTaskType,
    MobilityCommandType,
    PlatformType,
    ROEProfile,
    ThreatPriority,
)

Vector3 = tuple[float, float, float]


class TacticalBaseModel(BaseModel):
    """Strict base schema for tactical API payload validation."""

    model_config = ConfigDict(extra="forbid")


class TrackRequest(TacticalBaseModel):
    track_id: str = Field(..., min_length=1, max_length=128)
    position: Vector3
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)
    classification: str = Field(default="unknown", min_length=1, max_length=128)
    threat_priority: ThreatPriority = ThreatPriority.MEDIUM
    last_seen: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class TrackResponse(TrackRequest):
    pass


class MissionTaskRequest(TacticalBaseModel):
    task_type: MissionTaskType
    waypoints: list[Vector3] = Field(default_factory=list)


class MissionTaskResponse(MissionTaskRequest):
    pass


class PlatformStateRequest(TacticalBaseModel):
    platform_id: str = Field(..., min_length=1, max_length=128)
    platform_type: PlatformType
    position: Vector3
    health_state: HealthState = HealthState.NOMINAL
    autonomy_mode: AutonomyMode = AutonomyMode.SUPERVISED


class PlatformStateResponse(PlatformStateRequest):
    pass


class MobilityCommandRequest(TacticalBaseModel):
    command_type: MobilityCommandType
    target_position: Vector3 | None = None


class MobilityCommandResponse(MobilityCommandRequest):
    pass


class PayloadStateRequest(TacticalBaseModel):
    payload_id: str = Field(..., min_length=1, max_length=128)
    ammo_count: int = Field(..., ge=0)
    connected: bool = False


class PayloadStateResponse(PayloadStateRequest):
    pass


class OperatorAuthorizationRequest(TacticalBaseModel):
    operator_id: str = Field(..., min_length=1, max_length=128)
    auth_type: AuthorizationType
    auth_id: str | None = Field(default=None, min_length=1, max_length=128)


class OperatorAuthorizationResponse(TacticalBaseModel):
    operator_id: str = Field(..., min_length=1, max_length=128)
    auth_type: AuthorizationType
    auth_id: str = Field(..., min_length=1, max_length=128)


class SensorCommandRequest(TacticalBaseModel):
    sensor: str = Field(..., min_length=1, max_length=128)
    enabled: bool = True
    mode: str | None = Field(default=None, max_length=128)
    parameters: dict[str, Any] = Field(default_factory=dict)


class SafeStateRequest(TacticalBaseModel):
    reason: str = Field(default="operator_request", min_length=1, max_length=256)


class PlatformOperationResponse(TacticalBaseModel):
    platform_id: str
    operation: str
    success: bool
    connected: bool | None = None
    detail: str | None = None
    data: dict[str, Any] | None = None


class CommandDispatchResponse(TacticalBaseModel):
    platform_id: str
    command: Literal["mobility", "sensor", "safe-state"]
    accepted: bool
    detail: str
    data: dict[str, Any] = Field(default_factory=dict)


class PlatformStateEnvelope(TacticalBaseModel):
    platform_id: str
    state_type: Literal["platform", "payload", "raw"]
    platform_state: PlatformStateResponse | None = None
    payload_state: PayloadStateResponse | None = None
    raw_state: dict[str, Any] | None = None


class PlatformHealthResponse(TacticalBaseModel):
    platform_id: str
    adapter_class: str
    status: str
    connected: bool | None = None
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    diagnostics: dict[str, Any] = Field(default_factory=dict)


class PlatformCapabilitiesResponse(TacticalBaseModel):
    platform_id: str
    adapter_class: str
    domain: str
    supported_operations: list[str]
    governance: dict[str, Any] = Field(default_factory=dict)
    fire_control_policy: ROEProfile = ROEProfile.WEAPONS_TIGHT
    authority_levels: list[AuthorityLevel] = Field(
        default_factory=lambda: [
            AuthorityLevel.OPERATOR,
            AuthorityLevel.TEAM_LEAD,
            AuthorityLevel.MISSION_COMMANDER,
        ]
    )
    interlock_states: list[InterlockState] = Field(
        default_factory=lambda: [InterlockState.SAFE, InterlockState.ARMED, InterlockState.FIRING]
    )
