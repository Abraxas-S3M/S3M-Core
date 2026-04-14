"""Target allocator for layered air-defense effectors."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from services.air_defense.effector_registry import EffectorRegistry
from services.air_defense.models import DefenseEchelon, Effector
from services.air_defense.zone_manager import ZoneManager


@dataclass
class TargetAllocation:
    """Recorded assignment between a track and selected effector."""

    target_id: str
    target_type: str
    target_position: tuple[float, float, float]
    target_speed_mps: float
    effector_id: str
    zone_id: str
    pk_estimate: float


@dataclass
class AllocationResult:
    """Outcome of an allocation attempt."""

    allocated: bool
    allocation: Optional[TargetAllocation] = None
    reason: Optional[str] = None


class TargetAllocator:
    """Allocates tracks to the best tactical effector available."""

    _ECHELON_PRIORITY: dict[DefenseEchelon, int] = {
        DefenseEchelon.EXTENDED: 0,
        DefenseEchelon.MEDIUM: 1,
        DefenseEchelon.SHORT: 2,
        DefenseEchelon.CLOSE: 3,
    }

    def __init__(self, registry: EffectorRegistry, zone_manager: ZoneManager) -> None:
        self.registry = registry
        self.zone_manager = zone_manager

    def allocate(
        self,
        target_id: str,
        target_position: tuple[float, float, float],
        target_speed_mps: float,
        target_type: str,
        exclude_effector_ids: Optional[set[str]] = None,
    ) -> AllocationResult:
        """Assign a target to a zone-compatible effector.

        Military context:
        The allocator biases to outer echelons first so close-in systems remain
        available for terminal leakers.
        """
        zones = self.zone_manager.find_zones_for_target(target_position)
        if not zones:
            return AllocationResult(allocated=False, reason="target_out_of_defended_zones")

        zone_ids = {zone.zone_id for zone in zones}
        excluded = exclude_effector_ids or set()

        candidates = [
            eff
            for eff in self.registry.get_available_for_target(target_position, target_speed_mps)
            if eff.assigned_zone_id in zone_ids and eff.effector_id not in excluded
        ]
        if not candidates:
            return AllocationResult(allocated=False, reason="no_eligible_effectors")

        selected = self._select_best(candidates)
        selected.begin_engagement(target_id)
        assert selected.assigned_zone_id is not None

        return AllocationResult(
            allocated=True,
            allocation=TargetAllocation(
                target_id=target_id,
                target_type=target_type,
                target_position=target_position,
                target_speed_mps=target_speed_mps,
                effector_id=selected.effector_id,
                zone_id=selected.assigned_zone_id,
                pk_estimate=selected.envelope.pk_single_shot,
            ),
        )

    def _select_best(self, candidates: list[Effector]) -> Effector:
        """Sort candidates by echelon priority and immediate lethality."""
        return sorted(
            candidates,
            key=lambda eff: (
                self._ECHELON_PRIORITY.get(eff.echelon, 99),
                -eff.envelope.pk_single_shot,
                -eff.readiness_score,
                -eff.ammunition_remaining,
            ),
        )[0]

