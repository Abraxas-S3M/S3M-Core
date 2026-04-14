"""Registry for air-defense effectors."""

from __future__ import annotations

from typing import Dict, Iterable, List, Optional

from services.air_defense.models import Effector, EffectorCategory


class EffectorRegistry:
    """In-memory catalogue of effectors available to tactical allocation."""

    def __init__(self) -> None:
        self._effectors: Dict[str, Effector] = {}

    def register(self, effector: Effector) -> None:
        if effector.effector_id in self._effectors:
            raise ValueError(f"Effector {effector.effector_id} already registered")
        self._effectors[effector.effector_id] = effector

    def register_many(self, effectors: Iterable[Effector]) -> None:
        for effector in effectors:
            self.register(effector)

    def get(self, effector_id: str) -> Optional[Effector]:
        return self._effectors.get(effector_id)

    def list_all(self) -> List[Effector]:
        return list(self._effectors.values())

    def list_by_category(self, category: EffectorCategory) -> List[Effector]:
        return [eff for eff in self._effectors.values() if eff.category is category]
