"""Miss assessment and automatic reallocation workflow.

Military context:
Miss handling preserves layered defense by immediately pivoting to alternate
channels when first-shot intercepts fail against maneuvering threats.
"""

from __future__ import annotations

from typing import Dict, List, Optional, Sequence, Tuple

from services.air_defense.effector_registry import EffectorRegistry
from services.air_defense.models import AllocationResult, EffectorCategory, TargetAllocation
from services.air_defense.target_allocator import TargetAllocator


class MissHandler:
    """Assess misses and trigger deterministic fallback allocation policies."""

    def __init__(self, allocator: TargetAllocator, registry: EffectorRegistry) -> None:
        self.allocator = allocator
        self.registry = registry

    def handle_miss(
        self,
        *,
        target_id: str,
        target_position: Tuple[float, float, float],
        target_type: str,
        previous_allocation: Optional[TargetAllocation],
        miss_reason: str,
    ) -> AllocationResult:
        """Handle miss event and allocate next-best effector channel."""
        reason_text = str(miss_reason or "unknown").lower()
        excluded_ids = set()
        previous_category: Optional[EffectorCategory] = None
        if previous_allocation is not None:
            excluded_ids.add(previous_allocation.assigned_effector_id)
            self.registry.dequeue_target(previous_allocation.assigned_effector_id)
            self.registry.record_shot(previous_allocation.assigned_effector_id)
            previous_effector = self.registry.get_effector(previous_allocation.assigned_effector_id)
            if previous_effector is not None:
                previous_category = previous_effector.category

        fallback_plans = self._build_fallback_plan(
            target_type=str(target_type),
            miss_reason=reason_text,
            previous_category=previous_category,
        )

        aggregate_considered: List[TargetAllocation] = []
        aggregate_unavailable: Dict[str, str] = {}
        latest_queue_depth: Dict[str, int] = {}
        selected: Optional[TargetAllocation] = None

        for depth, category_plan in enumerate(fallback_plans, start=1):
            result = self.allocator.allocate_target(
                target_id=target_id,
                target_position=target_position,
                target_type=target_type,
                allowed_categories=category_plan,
                preferred_categories=category_plan,
                excluded_effector_ids=excluded_ids,
                reserve_queue=True,
                fallback_depth=depth,
            )
            aggregate_considered.extend(result.considered_allocations)
            for key, value in result.unavailable_reasons.items():
                aggregate_unavailable.setdefault(key, value)
            latest_queue_depth = result.queue_depth_by_effector
            if result.selected_allocation is not None:
                selected = result.selected_allocation
                break

        return AllocationResult(
            target_id=target_id,
            selected_allocation=selected,
            considered_allocations=aggregate_considered,
            unavailable_reasons=aggregate_unavailable,
            queue_depth_by_effector=latest_queue_depth,
            fallback_required=True,
        )

    @staticmethod
    def _build_fallback_plan(
        *,
        target_type: str,
        miss_reason: str,
        previous_category: Optional[EffectorCategory],
    ) -> List[Sequence[EffectorCategory]]:
        target_text = str(target_type).lower()
        if "drone" in miss_reason or "uav" in miss_reason or "drone" in target_text or "uav" in target_text:
            return [
                [EffectorCategory.MISSILE],
                [EffectorCategory.GUN, EffectorCategory.MANPADS],
                [EffectorCategory.DIRECTED_ENERGY, EffectorCategory.ELECTRONIC_WARFARE],
            ]
        if previous_category == EffectorCategory.MISSILE:
            return [
                [EffectorCategory.GUN, EffectorCategory.MANPADS],
                [EffectorCategory.MISSILE],
            ]
        if previous_category in {EffectorCategory.GUN, EffectorCategory.MANPADS}:
            return [
                [EffectorCategory.MISSILE],
                [EffectorCategory.GUN, EffectorCategory.MANPADS],
            ]
        return [
            [EffectorCategory.MISSILE],
            [EffectorCategory.GUN, EffectorCategory.MANPADS],
        ]
