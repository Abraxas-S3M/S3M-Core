"""Shared platform abstraction contracts and messages."""

from .contracts import PayloadAdapter, PlatformAdapter
from .platform_registry import PlatformRegistry, RegisteredPlatform
from .messages import (
    AuthorityLevel,
    AuthorizationType,
    AutonomyMode,
    HealthState,
    InterlockState,
    MissionTask,
    MissionTaskType,
    MobilityCommand,
    MobilityCommandType,
    OperatorAuthorization,
    PayloadState,
    PlatformState,
    PlatformType,
    ROEProfile,
    ThreatPriority,
    Track,
)

__all__ = [
    "PlatformAdapter",
    "PayloadAdapter",
    "PlatformType",
    "Track",
    "ThreatPriority",
    "MissionTask",
    "MissionTaskType",
    "PlatformState",
    "HealthState",
    "MobilityCommand",
    "MobilityCommandType",
    "AuthorizationType",
    "AuthorityLevel",
    "InterlockState",
    "OperatorAuthorization",
    "AutonomyMode",
    "ROEProfile",
    "PayloadState",
    "PlatformRegistry",
    "RegisteredPlatform",
]
