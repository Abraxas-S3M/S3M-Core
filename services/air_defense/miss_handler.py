"""Miss handling and fallback reallocation for layered defense."""

from __future__ import annotations

from services.air_defense.effector_registry import EffectorRegistry
from services.air_defense.target_allocator import AllocationResult, TargetAllocation, TargetAllocator


class MissHandler:
    """Handles interceptor misses and attempts fallback reassignment."""

    def __init__(self, registry: EffectorRegistry, allocator: TargetAllocator) -> None:
        self.registry = registry
        self.allocator = allocator

    def report_miss(
        self,
        previous_allocation: TargetAllocation,
        updated_target_position: tuple[float, float, float],
        updated_target_speed: float,
    ) -> AllocationResult:
        """Record miss on previous shooter and attempt tactical fallback."""
        prior_effector = self.registry.get(previous_allocation.effector_id)
        if prior_effector is not None:
            prior_effector.complete_engagement(kill=False)

        return self.allocator.allocate(
            target_id=previous_allocation.target_id,
            target_position=updated_target_position,
            target_speed_mps=updated_target_speed,
            target_type=previous_allocation.target_type,
            exclude_effector_ids={previous_allocation.effector_id},
        )

