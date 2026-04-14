"""Air defense engagement allocation services.

Military context:
Provides layered post-miss re-allocation to preserve engagement depth
against incoming aerial threats in contested air-defense zones.
"""

from services.air_defense.effector_registry import EffectorRegistry
from services.air_defense.miss_handler import MissHandler
from services.air_defense.models import (
    AllocationResult,
    Effector,
    EffectorCategory,
    EffectorEnvelope,
    EffectorState,
    TargetAllocation,
)
from services.air_defense.target_allocator import TargetAllocator

__all__ = [
    "AllocationResult",
    "Effector",
    "EffectorCategory",
    "EffectorEnvelope",
    "EffectorRegistry",
    "EffectorState",
    "MissHandler",
    "TargetAllocation",
    "TargetAllocator",
]
