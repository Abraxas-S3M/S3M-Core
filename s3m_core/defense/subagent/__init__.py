"""Subagent containment controls for S3M defensive runtime policy."""

from .keystroke_detector import (
    CommandEvent,
    KeystrokeSimulationDetector,
    SimulationDetection,
)
from .permission_inheritance import AgentInfo, PermissionInheritance, Violation
from .spawn_gate import SandboxConfig, SpawnDecision, SpawnGate, SpawnRequest

__all__ = [
    "AgentInfo",
    "CommandEvent",
    "KeystrokeSimulationDetector",
    "PermissionInheritance",
    "SandboxConfig",
    "SimulationDetection",
    "SpawnDecision",
    "SpawnGate",
    "SpawnRequest",
    "Violation",
]
