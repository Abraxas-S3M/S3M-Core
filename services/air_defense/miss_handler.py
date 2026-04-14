"""Post-engagement miss assessment and automatic re-allocation.

Military context:
Implements Krechet step 7: when an interceptor drone misses, the system
automatically redistributes the target to missile channels. When a missile
misses, it falls back to gun/MANPADS. This ensures layered engagement
depth - every target gets multiple engagement opportunities.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Dict, List, Optional, Tuple

from services.air_defense.effector_registry import EffectorRegistry
from services.air_defense.models import (
    AllocationResult,
    EffectorCategory,
    TargetAllocation,
)
from services.air_defense.target_allocator import TargetAllocator


# Fallback chain: interceptor drone -> SAM -> gun/MANPADS -> EW
FALLBACK_CHAIN: Dict[EffectorCategory, List[EffectorCategory]] = {
    EffectorCategory.INTERCEPTOR_DRONE: [
        EffectorCategory.SAM_MEDIUM,
        EffectorCategory.SAM_SHORT,
        EffectorCategory.CIWS_GUN,
        EffectorCategory.MANPADS,
    ],
    EffectorCategory.SAM_MEDIUM: [
        EffectorCategory.SAM_SHORT,
        EffectorCategory.CIWS_GUN,
        EffectorCategory.MANPADS,
    ],
    EffectorCategory.SAM_SHORT: [
        EffectorCategory.CIWS_GUN,
        EffectorCategory.MANPADS,
        EffectorCategory.ELECTRONIC_WARFARE,
    ],
    EffectorCategory.CIWS_GUN: [
        EffectorCategory.MANPADS,
        EffectorCategory.ELECTRONIC_WARFARE,
    ],
    EffectorCategory.MANPADS: [
        EffectorCategory.ELECTRONIC_WARFARE,
    ],
    EffectorCategory.ELECTRONIC_WARFARE: [],
}


class MissHandler:
    """Handle post-engagement misses with automatic fallback re-allocation."""

    def __init__(self, registry: EffectorRegistry, allocator: TargetAllocator) -> None:
        self.registry = registry
        self.allocator = allocator
        self._miss_log: List[Dict] = []

    def report_miss(
        self,
        allocation: TargetAllocation,
        updated_target_position: Optional[Tuple[float, float, float]] = None,
        updated_target_speed: Optional[float] = None,
    ) -> AllocationResult:
        """Process a miss and attempt re-allocation to fallback effector.

        Steps matching Krechet doctrine:
        1. Complete engagement on the original effector (mark miss).
        2. Update target position if provided (target may have moved).
        3. Determine fallback category chain.
        4. Exclude the original effector from candidates.
        5. Attempt re-allocation from fallback chain.
        """
        # Step 1: Release the original effector
        original_effector = self.registry.get(allocation.effector_id)
        if original_effector is not None:
            original_effector.complete_engagement(kill=False)

        allocation.status = "miss"
        allocation.attempts += 1

        # Record the miss for after-action analysis.
        self._miss_log.append(
            {
                "allocation_id": allocation.allocation_id,
                "target_id": allocation.target_id,
                "original_effector": allocation.effector_id,
                "original_category": (
                    original_effector.category.value if original_effector else "unknown"
                ),
                "attempt": allocation.attempts,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }
        )

        if allocation.attempts >= allocation.max_attempts:
            return AllocationResult(
                allocated=False,
                reasoning=(
                    f"Target {allocation.target_id} exceeded max engagement attempts "
                    f"({allocation.max_attempts})"
                ),
            )

        # Step 2: Update target state
        target_pos = updated_target_position or allocation.target_position
        target_speed = (
            updated_target_speed
            if updated_target_speed is not None
            else allocation.target_speed_mps
        )

        # Step 3-5: Build and apply fallback chain.
        if original_effector is not None:
            fallback_categories = FALLBACK_CHAIN.get(original_effector.category, [])
        else:
            fallback_categories = []
        allowed_categories = set(fallback_categories)

        # Try pre-computed fallback effectors first.
        for fb_id in allocation.fallback_effector_ids:
            fb_eff = self.registry.get(fb_id)
            if fb_eff is None:
                continue
            if fb_eff.effector_id == allocation.effector_id:
                continue
            if fb_eff.category not in allowed_categories:
                continue
            if fb_eff.can_engage(target_pos, target_speed):
                new_alloc = TargetAllocation(
                    target_id=allocation.target_id,
                    target_position=target_pos,
                    target_speed_mps=target_speed,
                    target_classification=allocation.target_classification,
                    effector_id=fb_eff.effector_id,
                    effector_type=fb_eff.effector_type,
                    echelon=fb_eff.echelon,
                    zone_id=fb_eff.assigned_zone_id or "",
                    slant_range_m=fb_eff.range_to(target_pos),
                    pk_estimate=fb_eff.envelope.pk_single_shot * fb_eff.readiness_score,
                    suitability_score=0.5,
                    reasoning=f"Fallback re-allocation after miss (attempt {allocation.attempts + 1})",
                    attempts=allocation.attempts,
                    max_attempts=allocation.max_attempts,
                )
                fb_eff.begin_engagement(allocation.target_id)
                return AllocationResult(
                    allocated=True,
                    allocation=new_alloc,
                    reasoning=f"Re-allocated to {fb_eff.name_en} after miss",
                    echelon_used=fb_eff.echelon,
                )

        # Full re-allocation through allocator, constrained by doctrinal fallback categories.
        result = self.allocator.allocate(
            target_id=allocation.target_id,
            target_position=target_pos,
            target_speed_mps=target_speed,
            target_classification=allocation.target_classification,
            preferred_categories=fallback_categories,
            excluded_effector_ids={allocation.effector_id},
        )
        if result.allocated and result.allocation:
            result.allocation.attempts = allocation.attempts
            result.allocation.max_attempts = allocation.max_attempts
            result.reasoning = f"Re-allocated to {result.allocation.effector_id} after miss"
        return result

    def report_kill(self, allocation: TargetAllocation) -> None:
        """Record a confirmed kill on the target."""
        effector = self.registry.get(allocation.effector_id)
        if effector is not None:
            effector.complete_engagement(kill=True)
        allocation.status = "hit"

    def get_miss_log(self, limit: int = 100) -> List[Dict]:
        return self._miss_log[-limit:]

    def get_miss_stats(self) -> Dict[str, int]:
        return {
            "total_misses": len(self._miss_log),
            "targets_with_misses": len(set(m["target_id"] for m in self._miss_log)),
        }
