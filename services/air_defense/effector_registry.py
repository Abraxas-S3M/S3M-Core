"""Registry for tactical air-defense effectors."""

from __future__ import annotations

from typing import Optional

from services.air_defense.models import DefenseEchelon, Effector, EffectorCategory, EffectorState


class EffectorRegistry:
    """In-memory index for querying and scoring defense effectors."""

    def __init__(self) -> None:
        self._effectors: dict[str, Effector] = {}

    def register(self, effector: Effector) -> None:
        """Register a single tactical effector."""
        self._effectors[effector.effector_id] = effector

    def get(self, effector_id: str) -> Optional[Effector]:
        """Get effector by unique identifier."""
        return self._effectors.get(effector_id)

    def count(self) -> int:
        """Return total registered effectors."""
        return len(self._effectors)

    def list_all(self) -> list[Effector]:
        """Return all registered effectors."""
        return list(self._effectors.values())

    def query(
        self,
        echelon: Optional[DefenseEchelon] = None,
        category: Optional[EffectorCategory] = None,
        state: Optional[EffectorState] = None,
    ) -> list[Effector]:
        """Filter effectors by tactical attributes."""
        output = self.list_all()
        if echelon is not None:
            output = [eff for eff in output if eff.echelon == echelon]
        if category is not None:
            output = [eff for eff in output if eff.category == category]
        if state is not None:
            output = [eff for eff in output if eff.state == state]
        return output

    def get_available_for_target(
        self,
        target_position: tuple[float, float, float],
        target_speed_mps: Optional[float] = None,
    ) -> list[Effector]:
        """Return available effectors that can legally engage target geometry."""
        return [
            eff
            for eff in self.list_all()
            if eff.can_engage(target_position, target_speed_mps=target_speed_mps)
        ]

    def get_stats(self) -> dict[str, int]:
        """Summarize tactical readiness for command dashboards."""
        total = self.count()
        ready = len([eff for eff in self.list_all() if eff.is_available])
        engaging = len([eff for eff in self.list_all() if eff.state == EffectorState.ENGAGING])
        depleted = len([eff for eff in self.list_all() if eff.state == EffectorState.DEPLETED])
        return {
            "total": total,
            "ready": ready,
            "engaging": engaging,
            "depleted": depleted,
        }

