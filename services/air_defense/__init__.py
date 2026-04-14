"""
S3M Air Defense Effector Registry and Zone Manager

Provides typed effector management, echeloned defense zones, and intelligent
target-to-effector allocation modeled on C2 Krechet 9C905 capabilities.

Subsystems:
- EffectorRegistry: typed catalog of all air defense assets with engagement envelopes
- ZoneManager: echeloned/layered defense zone spatial management
- TargetAllocator: smart target distribution across effector types and echelons
- MissHandler: post-engagement miss assessment and automatic re-allocation

Integration:
  Layer 02 (Sensor Fusion) -> fused tracks -> TargetAllocator -> EffectorRegistry
  Kill-chain F2T2EA pipeline calls TargetAllocator.allocate() at TARGET phase
"""

from services.air_defense.models import (
    EffectorType,
    EffectorCategory,
    DefenseEchelon,
    EngagementEnvelope,
    EffectorState,
    Effector,
    DefenseZone,
    AirDefenseUnit,
    TargetAllocation,
    AllocationResult,
)
from services.air_defense.effector_registry import EffectorRegistry
from services.air_defense.zone_manager import ZoneManager
from services.air_defense.target_allocator import TargetAllocator
from services.air_defense.miss_handler import MissHandler

__all__ = [
    "EffectorType",
    "EffectorCategory",
    "DefenseEchelon",
    "EngagementEnvelope",
    "EffectorState",
    "Effector",
    "DefenseZone",
    "AirDefenseUnit",
    "TargetAllocation",
    "AllocationResult",
    "EffectorRegistry",
    "ZoneManager",
    "TargetAllocator",
    "MissHandler",
]
