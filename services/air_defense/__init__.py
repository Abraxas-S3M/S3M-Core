"""Air defense effector registry and echeloned zone subsystem.

Military context:
This package models layered, sovereign air-defense orchestration so commanders
can allocate effectors with deterministic fallback behavior under contested
airspace conditions without external connectivity.
"""

from services.air_defense.effector_registry import EffectorRegistry
from services.air_defense.miss_handler import MissHandler
from services.air_defense.models import (
    AirDefenseUnit,
    AllocationResult,
    DefenseEchelon,
    DefenseZone,
    Effector,
    EffectorCategory,
    EffectorState,
    EffectorType,
    EngagementEnvelope,
    TargetAllocation,
)
from services.air_defense.target_allocator import TargetAllocator
from services.air_defense.zone_manager import DefenseZoneManager

__all__ = [
    "AirDefenseUnit",
    "AllocationResult",
    "DefenseEchelon",
    "DefenseZone",
    "DefenseZoneManager",
    "Effector",
    "EffectorCategory",
    "EffectorRegistry",
    "EffectorState",
    "EffectorType",
    "EngagementEnvelope",
    "MissHandler",
    "TargetAllocation",
    "TargetAllocator",
]
