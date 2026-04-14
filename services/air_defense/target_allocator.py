"""Target allocator for layered air-defense effector assignment.

Military context:
Allocator logic selects the best available interceptor while preserving a
transparent rationale for post-action review and command accountability.
"""

from __future__ import annotations

import math
import uuid
from typing import List, Tuple

from services.air_defense.effector_registry import EffectorRegistry
from services.air_defense.models import AllocationDecision, AllocationRecord, DefenseEchelon, Effector
from services.air_defense.zone_manager import ZoneManager


class TargetAllocator:
    """Assign targets to effectors using deterministic scoring."""

    def __init__(self, registry: EffectorRegistry, zone_manager: ZoneManager) -> None:
        self.registry = registry
        self.zone_manager = zone_manager
        self._allocation_log: List[AllocationRecord] = []

    @staticmethod
    def _candidate_score(effector: Effector, target_position: Tuple[float, float, float], target_speed_mps: float) -> float:
        distance = math.dist(effector.position, target_position)
        if distance > effector.max_range_m:
            return -1.0
        range_score = 1.0 - min(1.0, distance / max(effector.max_range_m, 1.0))
        ammo_score = effector.ammunition_remaining / max(effector.ammunition_capacity, 1)
        # Tactical context: faster targets benefit from interceptors with margin,
        # so we slightly damp scores as target speed grows.
        speed_penalty = min(0.2, max(0.0, target_speed_mps) / 4000.0)
        return max(0.0, (0.65 * range_score) + (0.35 * ammo_score) - speed_penalty)

    def allocate(
        self,
        target_id: str,
        position: Tuple[float, float, float],
        speed_mps: float,
        classification: str,
    ) -> AllocationDecision:
        """Allocate a target to the highest-scoring available effector."""
        if not target_id:
            return AllocationDecision(
                allocated=False,
                allocation=None,
                alternatives_count=0,
                echelon_used=None,
                reasoning="target_id missing",
            )

        covering = self.zone_manager.zones_covering_position(position)
        prioritized_echelons = [zone.echelon for zone in covering]
        if not prioritized_echelons:
            prioritized_echelons = [
                DefenseEchelon.SHORT_RANGE,
                DefenseEchelon.MEDIUM_RANGE,
                DefenseEchelon.LONG_RANGE,
            ]

        all_candidates: List[tuple[Effector, float]] = []
        chosen_echelon: DefenseEchelon | None = None
        for echelon in prioritized_echelons:
            echelon_candidates: List[tuple[Effector, float]] = []
            for effector in self.registry.query(available_only=True, echelon=echelon):
                score = self._candidate_score(effector, position, speed_mps)
                if score >= 0.0:
                    echelon_candidates.append((effector, score))
            if echelon_candidates:
                all_candidates = echelon_candidates
                chosen_echelon = echelon
                break

        if not all_candidates:
            return AllocationDecision(
                allocated=False,
                allocation=None,
                alternatives_count=0,
                echelon_used=None,
                reasoning="No available effector within engagement envelope",
            )

        all_candidates.sort(key=lambda item: item[1], reverse=True)
        winner, winner_score = all_candidates[0]
        self.registry.consume_round(winner.effector_id, rounds=1)

        allocation = AllocationRecord(
            allocation_id=f"alloc-{uuid.uuid4().hex[:12]}",
            target_id=target_id,
            effector_id=winner.effector_id,
            target_position=position,
            target_speed_mps=float(speed_mps),
            classification=classification,
            echelon=chosen_echelon or winner.echelon,
            score=winner_score,
            reasoning=(
                f"Selected {winner.effector_id} ({winner.echelon.value}) for {classification} "
                f"at score {winner_score:.3f}"
            ),
        )
        self._allocation_log.append(allocation)
        return AllocationDecision(
            allocated=True,
            allocation=allocation,
            alternatives_count=max(0, len(all_candidates) - 1),
            echelon_used=allocation.echelon,
            reasoning=allocation.reasoning,
        )

    def get_allocation_log(self, limit: int = 50) -> List[AllocationRecord]:
        """Return most-recent allocation decisions first."""
        safe_limit = max(1, min(int(limit), 10_000))
        return list(reversed(self._allocation_log[-safe_limit:]))

