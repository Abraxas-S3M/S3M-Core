"""Registry for air-defense effectors and engagement availability.

Military context:
Maintains authoritative fire-unit state for layered defense planning so
allocators can rapidly choose viable effectors under combat constraints.
"""

from __future__ import annotations

from typing import Dict, List, Optional, Tuple

from services.air_defense.models import (
    DefenseEchelon,
    Effector,
    EffectorCategory,
)


class EffectorRegistry:
    """Store and query tactical effectors by readiness and geometry."""

    def __init__(self, effectors: Optional[List[Effector]] = None) -> None:
        self._effectors: Dict[str, Effector] = {}
        for effector in effectors or []:
            self.register(effector)

    def register(self, effector: Effector) -> None:
        """Register or replace an effector state entry."""
        self._effectors[effector.effector_id] = effector

    def get(self, effector_id: str) -> Optional[Effector]:
        return self._effectors.get(effector_id)

    def list_all(self) -> List[Effector]:
        return sorted(self._effectors.values(), key=lambda item: item.effector_id)

    def query(
        self,
        zone_id: Optional[str] = None,
        available_only: bool = False,
        echelon: Optional[DefenseEchelon] = None,
        category: Optional[EffectorCategory] = None,
    ) -> List[Effector]:
        """Query effectors by zone, tactical role, and readiness."""
        effectors = self.list_all()
        if zone_id:
            effectors = [eff for eff in effectors if eff.zone_id == zone_id]
        if echelon:
            effectors = [eff for eff in effectors if eff.echelon == echelon]
        if category:
            effectors = [eff for eff in effectors if eff.category == category]
        if available_only:
            effectors = [eff for eff in effectors if eff.is_available()]
        return effectors

    def get_available_for_target(
        self, target_position: Tuple[float, float, float], target_speed_mps: float
    ) -> List[Effector]:
        """Return all currently available effectors that can engage this target."""
        candidates = [
            eff
            for eff in self._effectors.values()
            if eff.can_engage(target_position, target_speed_mps)
        ]
        return sorted(
            candidates,
            key=lambda eff: (-eff.readiness_score, eff.range_to(target_position)),
        )
