"""Target allocator for layered air-defense effectors.

Military context:
Implements deterministic category-priority allocation so local batteries can
assign targets through missile-gun-EW layers without cloud dependencies.
"""

from __future__ import annotations

from typing import Iterable, Optional, Set

from services.air_defense.effector_registry import EffectorRegistry
from services.air_defense.models import (
    AllocationResult,
    Effector,
    EffectorCategory,
    TargetAllocation,
)


class TargetAllocator:
    """Allocate the best available effector for a target."""

    CATEGORY_PRIORITY = (
        EffectorCategory.INTERCEPTOR_DRONE,
        EffectorCategory.SAM_MEDIUM,
        EffectorCategory.SAM_SHORT,
        EffectorCategory.CIWS_GUN,
        EffectorCategory.MANPADS,
        EffectorCategory.ELECTRONIC_WARFARE,
    )

    def __init__(self, registry: EffectorRegistry) -> None:
        self.registry = registry

    def allocate(
        self,
        target_id: str,
        target_position: tuple[float, float, float],
        target_speed_mps: float,
        target_classification: str,
        preferred_categories: Optional[Iterable[EffectorCategory]] = None,
        excluded_effector_ids: Optional[Set[str]] = None,
    ) -> AllocationResult:
        """Allocate by category priority and in-envelope readiness."""
        categories = (
            tuple(preferred_categories)
            if preferred_categories is not None
            else self.CATEGORY_PRIORITY
        )
        excluded = excluded_effector_ids or set()
        for category in categories:
            selected = self._select_candidate(
                category,
                target_position,
                target_speed_mps,
                excluded_effector_ids=excluded,
            )
            if selected is None:
                continue
            selected.begin_engagement(target_id)
            allocation = TargetAllocation(
                target_id=target_id,
                target_position=target_position,
                target_speed_mps=target_speed_mps,
                target_classification=target_classification,
                effector_id=selected.effector_id,
                effector_type=selected.effector_type,
                echelon=selected.echelon,
                zone_id=selected.assigned_zone_id or "",
                slant_range_m=selected.range_to(target_position),
                pk_estimate=selected.envelope.pk_single_shot * selected.readiness_score,
                suitability_score=selected.readiness_score,
                reasoning=f"Allocated by category priority: {category.value}",
            )
            return AllocationResult(
                allocated=True,
                allocation=allocation,
                reasoning=f"Allocated to {selected.name_en}",
                echelon_used=selected.echelon,
            )
        return AllocationResult(
            allocated=False,
            reasoning="No available in-envelope effectors for target",
        )

    def _select_candidate(
        self,
        category: EffectorCategory,
        target_position: tuple[float, float, float],
        target_speed_mps: float,
        excluded_effector_ids: Set[str],
    ) -> Optional[Effector]:
        candidates = [
            eff
            for eff in self.registry.list_all()
            if (
                eff.category == category
                and eff.effector_id not in excluded_effector_ids
                and eff.can_engage(target_position, target_speed_mps)
            )
        ]
        if not candidates:
            return None
        return max(candidates, key=lambda eff: eff.readiness_score)
