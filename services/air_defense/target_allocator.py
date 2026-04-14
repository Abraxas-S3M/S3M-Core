"""Intelligent target-to-effector allocation engine.

Military context:
Implements Krechet 9C905-style fire distribution logic: when a target enters
defended airspace, the allocator determines which effector is best suited to
engage it based on envelope geometry, readiness, echelon doctrine (engage at
max range first), and effector suitability scoring.
"""

from __future__ import annotations

from math import isfinite
from typing import Dict, List, Optional, Tuple

from services.air_defense.effector_registry import EffectorRegistry
from services.air_defense.models import (
    AllocationResult,
    DefenseEchelon,
    Effector,
    EffectorCategory,
    TargetAllocation,
)
from services.air_defense.zone_manager import ZoneManager


ECHELON_PRIORITY = [
    DefenseEchelon.EXTENDED,
    DefenseEchelon.MEDIUM,
    DefenseEchelon.SHORT,
    DefenseEchelon.CLOSE,
]
_ECHELON_INDEX = {echelon: idx for idx, echelon in enumerate(ECHELON_PRIORITY)}

# Target classification to preferred effector category mapping.
TARGET_CATEGORY_PREFERENCE = {
    "ENEMY_UAV": [
        EffectorCategory.INTERCEPTOR_DRONE,
        EffectorCategory.SAM_SHORT,
        EffectorCategory.CIWS_GUN,
        EffectorCategory.ELECTRONIC_WARFARE,
    ],
    "ENEMY_CRUISE_MISSILE": [
        EffectorCategory.SAM_MEDIUM,
        EffectorCategory.SAM_SHORT,
        EffectorCategory.CIWS_GUN,
    ],
    "ENEMY_HELICOPTER": [
        EffectorCategory.SAM_SHORT,
        EffectorCategory.MANPADS,
        EffectorCategory.CIWS_GUN,
    ],
    "ENEMY_AIRCRAFT": [
        EffectorCategory.SAM_MEDIUM,
        EffectorCategory.SAM_SHORT,
    ],
    "ENEMY_BALLISTIC": [
        EffectorCategory.SAM_MEDIUM,
    ],
    "UNKNOWN": [
        EffectorCategory.SAM_SHORT,
        EffectorCategory.CIWS_GUN,
        EffectorCategory.INTERCEPTOR_DRONE,
    ],
}


class TargetAllocator:
    """Allocate aerial targets to the best available effector."""

    def __init__(self, registry: EffectorRegistry, zone_manager: ZoneManager) -> None:
        self.registry = registry
        self.zone_manager = zone_manager
        self._allocation_log: List[TargetAllocation] = []

    def allocate(
        self,
        target_id: str,
        target_position: Tuple[float, float, float],
        target_speed_mps: float = 0.0,
        target_classification: str = "UNKNOWN",
    ) -> AllocationResult:
        """Find and assign the best effector for a target."""
        _validate_target_inputs(
            target_id=target_id,
            target_position=target_position,
            target_speed_mps=target_speed_mps,
            target_classification=target_classification,
        )

        zones = self.zone_manager.find_zones_for_target(target_position)
        zones = sorted(
            zones,
            key=lambda zone: _ECHELON_INDEX.get(zone.echelon, len(ECHELON_PRIORITY)),
        )
        if not zones:
            return AllocationResult(
                allocated=False,
                reasoning="Target outside all defense zones",
            )

        preferences = TARGET_CATEGORY_PREFERENCE.get(
            target_classification.upper(),
            TARGET_CATEGORY_PREFERENCE["UNKNOWN"],
        )

        best_score = -1.0
        best_effector: Optional[Effector] = None
        best_zone_id = ""
        alternatives_by_id: Dict[str, Effector] = {}

        for zone in zones:
            zone_effectors = self.registry.query(
                zone_id=zone.zone_id,
                available_only=True,
            )
            geometric_candidates = self.registry.get_available_for_target(
                target_position, target_speed_mps
            )

            seen = set()
            candidates: List[Effector] = []
            for eff in zone_effectors + geometric_candidates:
                if eff.effector_id not in seen:
                    seen.add(eff.effector_id)
                    candidates.append(eff)

            for eff in candidates:
                score = self._score_effector(
                    eff, target_position, target_speed_mps, preferences
                )
                if score < 0.0:
                    continue
                if score > best_score:
                    if best_effector is not None:
                        alternatives_by_id.setdefault(
                            best_effector.effector_id, best_effector
                        )
                    best_score = score
                    best_effector = eff
                    best_zone_id = zone.zone_id
                elif best_effector is None or eff.effector_id != best_effector.effector_id:
                    alternatives_by_id.setdefault(eff.effector_id, eff)

        if best_effector is None:
            return AllocationResult(
                allocated=False,
                reasoning="No available effector can engage target at current position",
                alternatives_count=0,
            )

        slant_range = best_effector.range_to(target_position)
        fallback_ids = list(alternatives_by_id.keys())[:3]

        allocation = TargetAllocation(
            target_id=target_id,
            target_position=target_position,
            target_speed_mps=target_speed_mps,
            target_classification=target_classification,
            effector_id=best_effector.effector_id,
            effector_type=best_effector.effector_type,
            echelon=best_effector.echelon,
            zone_id=best_zone_id,
            slant_range_m=slant_range,
            pk_estimate=min(
                1.0,
                best_effector.envelope.pk_single_shot * best_effector.readiness_score,
            ),
            suitability_score=best_score,
            reasoning=self._build_reasoning(
                best_effector,
                target_classification,
                slant_range,
                best_score,
            ),
            fallback_effector_ids=fallback_ids,
        )

        best_effector.begin_engagement(target_id)
        self._allocation_log.append(allocation)

        return AllocationResult(
            allocated=True,
            allocation=allocation,
            alternatives_count=len(alternatives_by_id),
            reasoning=allocation.reasoning,
            echelon_used=best_effector.echelon,
        )

    def _score_effector(
        self,
        effector: Effector,
        target_position: Tuple[float, float, float],
        target_speed_mps: float,
        category_preferences: List[EffectorCategory],
    ) -> float:
        """Compute composite suitability score for an effector-target pair."""
        if not effector.can_engage(target_position, target_speed_mps):
            return -1.0

        score = 0.0

        # Category preference bonus keeps engagements aligned with doctrine.
        if effector.category in category_preferences:
            rank = category_preferences.index(effector.category)
            score += max(0.0, 0.35 - rank * 0.08)

        score += effector.readiness_score * 0.25
        score += effector.envelope.pk_single_shot * 0.20

        slant_range = effector.range_to(target_position)
        range_ratio = slant_range / max(1.0, effector.envelope.max_range_m)
        if 0.4 <= range_ratio <= 0.8:
            score += 0.10
        elif 0.2 <= range_ratio <= 0.95:
            score += 0.05

        speed_ratio = target_speed_mps / max(1.0, effector.envelope.max_target_speed_mps)
        if speed_ratio <= 0.7:
            score += 0.05
        elif speed_ratio <= 1.0:
            score += 0.02

        echelon_bonus = {
            DefenseEchelon.EXTENDED: 0.10,
            DefenseEchelon.MEDIUM: 0.08,
            DefenseEchelon.SHORT: 0.05,
            DefenseEchelon.CLOSE: 0.02,
        }
        score += echelon_bonus.get(effector.echelon, 0.0)

        return min(1.0, score)

    def _build_reasoning(
        self, effector: Effector, target_class: str, slant_range: float, score: float
    ) -> str:
        return (
            f"Allocated {effector.name_en} ({effector.effector_type.value}) "
            f"in {effector.echelon.value} echelon for {target_class} target at "
            f"{slant_range:.0f}m slant range. Suitability score: {score:.2f}. "
            f"Ammo: {effector.ammunition_remaining}/{effector.ammunition_total}."
        )

    def get_allocation_log(self, limit: int = 50) -> List[TargetAllocation]:
        if limit <= 0:
            return []
        return self._allocation_log[-limit:]


def _validate_target_inputs(
    target_id: str,
    target_position: Tuple[float, float, float],
    target_speed_mps: float,
    target_classification: str,
) -> None:
    if not target_id.strip():
        raise ValueError("target_id must be non-empty")
    if len(target_position) != 3 or not all(isfinite(value) for value in target_position):
        raise ValueError("target_position must be three finite values")
    if target_speed_mps < 0 or not isfinite(target_speed_mps):
        raise ValueError("target_speed_mps must be finite and >= 0")
    if not target_classification.strip():
        raise ValueError("target_classification must be non-empty")
