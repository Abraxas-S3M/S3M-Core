"""Effector registry for air-defense readiness and inventory tracking.

Military context:
This registry is the local source of truth for launcher/gun readiness so the
tactical allocator can avoid assigning unavailable or depleted effectors.
"""

from __future__ import annotations

from collections import Counter
from typing import Dict, List, Optional

from services.air_defense.models import DefenseEchelon, Effector, EffectorCategory, EffectorState


class EffectorRegistry:
    """In-memory effector registry optimized for disconnected edge operation."""

    def __init__(self) -> None:
        self._effectors: Dict[str, Effector] = {}

    def register(self, effector: Effector) -> None:
        """Insert or update an effector in the registry."""
        self._effectors[effector.effector_id] = effector

    def get(self, effector_id: str) -> Optional[Effector]:
        """Return effector by identifier when present."""
        return self._effectors.get(effector_id)

    def query(
        self,
        *,
        available_only: bool = False,
        category: Optional[EffectorCategory] = None,
        echelon: Optional[DefenseEchelon] = None,
    ) -> List[Effector]:
        """Query effectors with optional readiness, category, and echelon filters."""
        effectors = list(self._effectors.values())
        if available_only:
            effectors = [eff for eff in effectors if eff.is_available()]
        if category is not None:
            effectors = [eff for eff in effectors if eff.category == category]
        if echelon is not None:
            effectors = [eff for eff in effectors if eff.echelon == echelon]
        return effectors

    def update_state(self, effector_id: str, new_state: EffectorState) -> bool:
        """Update state for a known effector."""
        effector = self.get(effector_id)
        if effector is None:
            return False
        effector.state = new_state
        return True

    def consume_round(self, effector_id: str, rounds: int = 1) -> bool:
        """Consume ammunition after launch authorization."""
        effector = self.get(effector_id)
        if effector is None:
            return False
        if rounds <= 0 or effector.ammunition_remaining < rounds:
            return False
        effector.ammunition_remaining -= rounds
        if effector.ammunition_remaining == 0:
            effector.state = EffectorState.RELOADING
        elif effector.state == EffectorState.ENGAGING:
            effector.state = EffectorState.READY
        return True

    def resupply(self, effector_id: str, rounds: Optional[int]) -> bool:
        """Resupply ammunition from logistics payload."""
        effector = self.get(effector_id)
        if effector is None:
            return False
        if rounds is None:
            effector.ammunition_remaining = effector.ammunition_capacity
        else:
            if rounds < 0:
                return False
            effector.ammunition_remaining = min(
                effector.ammunition_capacity,
                effector.ammunition_remaining + int(rounds),
            )
        if effector.ammunition_remaining > 0 and effector.state in {EffectorState.RELOADING, EffectorState.READY}:
            effector.state = EffectorState.READY
        return True

    def get_stats(self) -> Dict[str, object]:
        """Return summary metrics for operator readiness dashboards."""
        effectors = list(self._effectors.values())
        state_counter = Counter(eff.state.value for eff in effectors)
        category_counter = Counter(eff.category.value for eff in effectors)
        echelon_counter = Counter(eff.echelon.value for eff in effectors)
        return {
            "total_effectors": len(effectors),
            "available_effectors": sum(1 for eff in effectors if eff.is_available()),
            "states": dict(state_counter),
            "categories": dict(category_counter),
            "echelons": dict(echelon_counter),
            "total_ammunition_remaining": sum(eff.ammunition_remaining for eff in effectors),
        }

