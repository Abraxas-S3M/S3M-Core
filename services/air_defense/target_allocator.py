"""Target-to-effector allocation engine for layered air defense.

Military context:
Allocator logic enforces doctrinal outer-layer intercept first, then controlled
fallback to inner rings while preserving ammunition and launcher readiness.
"""

from __future__ import annotations

import time
import uuid
from typing import Dict, Iterable, List, Optional, Sequence, Set, Tuple

from services.air_defense.effector_registry import EffectorRegistry
from services.air_defense.models import (
    AllocationResult,
    DefenseEchelon,
    Effector,
    EffectorCategory,
    TargetAllocation,
)
from services.air_defense.zone_manager import DefenseZoneManager


class TargetAllocator:
    """Allocate targets to the best ready effector under layered doctrine."""

    ECHELON_ORDER = [DefenseEchelon.MEDIUM, DefenseEchelon.SHORT, DefenseEchelon.CLOSE]
    ECHELON_SCORE = {
        DefenseEchelon.MEDIUM: 58.0,
        DefenseEchelon.SHORT: 40.0,
        DefenseEchelon.CLOSE: 22.0,
    }

    def __init__(self, registry: EffectorRegistry, zone_manager: DefenseZoneManager) -> None:
        self.registry = registry
        self.zone_manager = zone_manager

    def allocate_target(
        self,
        *,
        target_id: str,
        target_position: Tuple[float, float, float],
        target_type: str = "unknown",
        rounds_required: int = 1,
        allowed_categories: Optional[Sequence[EffectorCategory]] = None,
        preferred_categories: Optional[Sequence[EffectorCategory]] = None,
        excluded_effector_ids: Optional[Iterable[str]] = None,
        reserve_queue: bool = True,
        now_ts: Optional[float] = None,
        fallback_depth: int = 0,
    ) -> AllocationResult:
        """Allocate one target based on geometry, readiness, and echelon doctrine."""
        now = time.time() if now_ts is None else float(now_ts)
        if len(target_position) != 3:
            raise ValueError("target_position must have three coordinates")
        target_type_text = str(target_type or "unknown")
        excluded: Set[str] = {str(value) for value in (excluded_effector_ids or [])}
        allowed = set(allowed_categories or [])
        preferred_order = list(preferred_categories or [])
        preferred_rank = {category: idx for idx, category in enumerate(preferred_order)}

        covering_zones = self.zone_manager.get_covering_zones(
            x_km=float(target_position[0]),
            y_km=float(target_position[1]),
            altitude_m=float(target_position[2]),
        )
        allowed_zone_ids = {zone.zone_id for zone in covering_zones}

        considered: List[TargetAllocation] = []
        unavailable: Dict[str, str] = {}
        queue_depths: Dict[str, int] = {}

        for effector in self.registry.list_effectors():
            self.registry.refresh_reload_state(effector.effector_id, now_ts=now)
            queue_depths[effector.effector_id] = self.registry.queue_depth(effector.effector_id)

            reason = self._effector_rejection_reason(
                effector=effector,
                target_position=target_position,
                allowed_zone_ids=allowed_zone_ids,
                excluded_effector_ids=excluded,
                allowed_categories=allowed,
                rounds_required=rounds_required,
                now_ts=now,
            )
            if reason:
                unavailable[effector.effector_id] = reason
                continue

            score = self._score_candidate(
                effector=effector,
                target_position=target_position,
                preferred_rank=preferred_rank,
                queue_depth=queue_depths[effector.effector_id],
            )
            considered.append(
                TargetAllocation(
                    allocation_id=f"alloc-{uuid.uuid4().hex[:12]}",
                    target_id=str(target_id),
                    target_type=target_type_text,
                    target_position=target_position,
                    assigned_effector_id=effector.effector_id,
                    echelon=effector.echelon,
                    score=score,
                    reason=self._build_reason(effector=effector, score=score),
                    queued_index=queue_depths[effector.effector_id],
                    fallback_depth=fallback_depth,
                    created_at=now,
                )
            )

        considered.sort(
            key=lambda alloc: (
                self.ECHELON_ORDER.index(alloc.echelon),
                -alloc.score,
                alloc.assigned_effector_id,
            )
        )

        selected: Optional[TargetAllocation] = None
        for echelon in self.ECHELON_ORDER:
            echelon_candidates = [alloc for alloc in considered if alloc.echelon == echelon]
            if echelon_candidates:
                selected = sorted(echelon_candidates, key=lambda alloc: (-alloc.score, alloc.assigned_effector_id))[0]
                break

        if selected is not None and reserve_queue:
            selected.queued_index = self.registry.enqueue_target(selected.assigned_effector_id)
            queue_depths[selected.assigned_effector_id] = selected.queued_index

        return AllocationResult(
            target_id=str(target_id),
            selected_allocation=selected,
            considered_allocations=considered,
            unavailable_reasons=unavailable,
            queue_depth_by_effector=queue_depths,
            fallback_required=fallback_depth > 0 or selected is None,
        )

    def allocate_many(self, targets: Sequence[Dict[str, object]]) -> List[AllocationResult]:
        """Allocate multiple targets in order while tracking queue pressure."""
        results: List[AllocationResult] = []
        for index, target in enumerate(targets):
            target_id = str(target.get("target_id", f"target-{index+1}"))
            position_raw = target.get("target_position", (0.0, 0.0, 0.0))
            if not isinstance(position_raw, (tuple, list)) or len(position_raw) != 3:
                raise ValueError("target_position must be a 3-element sequence")
            result = self.allocate_target(
                target_id=target_id,
                target_position=(float(position_raw[0]), float(position_raw[1]), float(position_raw[2])),
                target_type=str(target.get("target_type", "unknown")),
                reserve_queue=True,
                fallback_depth=int(target.get("fallback_depth", 0)),
            )
            results.append(result)
        return results

    def release_allocation(self, allocation: TargetAllocation) -> int:
        """Release queued slot after engagement completion or cancellation."""
        return self.registry.dequeue_target(allocation.assigned_effector_id)

    def _effector_rejection_reason(
        self,
        *,
        effector: Effector,
        target_position: Tuple[float, float, float],
        allowed_zone_ids: Set[str],
        excluded_effector_ids: Set[str],
        allowed_categories: Set[EffectorCategory],
        rounds_required: int,
        now_ts: float,
    ) -> str:
        if effector.effector_id in excluded_effector_ids:
            return "excluded_by_policy"
        if allowed_zone_ids and effector.zone_id not in allowed_zone_ids:
            return "target_outside_effector_zone"
        if allowed_categories and effector.category not in allowed_categories:
            return "category_not_allowed"
        if not effector.state.has_ammunition(rounds_required=rounds_required):
            return "insufficient_ammunition"
        if not effector.state.is_ready(now_ts=now_ts, rounds_required=rounds_required):
            return f"not_ready_status_{effector.state.status}"

        range_km = effector.ground_range_km_to(target_position)
        azimuth = effector.azimuth_to(target_position)
        altitude = float(target_position[2])
        if not effector.envelope.covers_range(range_km):
            return "outside_range_envelope"
        if not effector.envelope.covers_altitude(altitude):
            return "outside_altitude_envelope"
        if not effector.envelope.covers_azimuth(azimuth):
            return "outside_azimuth_envelope"
        return ""

    def _score_candidate(
        self,
        *,
        effector: Effector,
        target_position: Tuple[float, float, float],
        preferred_rank: Dict[EffectorCategory, int],
        queue_depth: int,
    ) -> float:
        range_km = effector.ground_range_km_to(target_position)
        altitude = float(target_position[2])
        envelope = effector.envelope

        range_mid = (envelope.min_range_km + envelope.max_range_km) * 0.5
        range_half = max(0.1, (envelope.max_range_km - envelope.min_range_km) * 0.5)
        altitude_mid = (envelope.min_altitude_m + envelope.max_altitude_m) * 0.5
        altitude_half = max(10.0, (envelope.max_altitude_m - envelope.min_altitude_m) * 0.5)

        range_fit = max(0.0, 1.0 - abs(range_km - range_mid) / range_half)
        engagement_span = max(0.1, envelope.max_range_km - envelope.min_range_km)
        # Tactical doctrine: prefer interceptors that can prosecute farther out
        # in their available envelope before collapsing to inner layers.
        outer_range_bias = max(0.0, min(1.0, (range_km - envelope.min_range_km) / engagement_span))
        altitude_fit = max(0.0, 1.0 - abs(altitude - altitude_mid) / altitude_half)
        ammo_ratio = (
            1.0
            if effector.state.ammunition_capacity == 0
            else effector.state.ammunition_current / float(effector.state.ammunition_capacity)
        )
        priority_bonus = max(0.0, 10.0 - min(1000.0, float(effector.priority)) * 0.05)
        category_bonus = 0.0
        if preferred_rank:
            if effector.category in preferred_rank:
                category_bonus = max(0.0, 8.0 - preferred_rank[effector.category] * 2.0)
            else:
                category_bonus = -4.0
        queue_penalty = min(30.0, max(0, int(queue_depth)) * 3.0)

        score = (
            self.ECHELON_SCORE[effector.echelon]
            + range_fit * 10.0
            + outer_range_bias * 6.0
            + altitude_fit * 5.0
            + effector.state.readiness * 8.0
            + ammo_ratio * 6.0
            + priority_bonus
            + category_bonus
            - queue_penalty
        )
        return max(0.0, min(100.0, score))

    @staticmethod
    def _build_reason(effector: Effector, score: float) -> str:
        return (
            f"echelon={effector.echelon.value}; category={effector.category.value}; "
            f"type={effector.effector_type.value}; score={score:.2f}"
        )
