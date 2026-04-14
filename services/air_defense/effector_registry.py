"""Thread-safe effector registry for air defense asset management.

Military context:
Central catalog of all air defense effectors under C2 control. Provides
typed queries by category, echelon, state, and zone — the foundation for
intelligent target allocation matching Krechet 9C905 fire distribution.
"""

from __future__ import annotations

import threading
from typing import Dict, List, Optional

from services.air_defense.models import (
    DefenseEchelon,
    Effector,
    EffectorCategory,
    EffectorState,
    EffectorType,
)


class EffectorRegistry:
    """Manages the complete inventory of air defense effectors."""

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._effectors: Dict[str, Effector] = {}

    def register(self, effector: Effector) -> Effector:
        """Register a new effector in the catalog."""
        if not isinstance(effector, Effector):
            raise ValueError("effector must be an Effector instance")
        with self._lock:
            self._effectors[effector.effector_id] = effector
        return effector

    def remove(self, effector_id: str) -> bool:
        """Remove an effector from the catalog."""
        with self._lock:
            return self._effectors.pop(effector_id, None) is not None

    def get(self, effector_id: str) -> Optional[Effector]:
        """Retrieve a single effector by ID."""
        with self._lock:
            return self._effectors.get(effector_id)

    def list_all(self) -> List[Effector]:
        """Return all registered effectors."""
        with self._lock:
            return list(self._effectors.values())

    def query(
        self,
        category: Optional[EffectorCategory] = None,
        echelon: Optional[DefenseEchelon] = None,
        state: Optional[EffectorState] = None,
        effector_type: Optional[EffectorType] = None,
        zone_id: Optional[str] = None,
        available_only: bool = False,
    ) -> List[Effector]:
        """Query effectors with optional filters."""
        with self._lock:
            results = list(self._effectors.values())
        if category is not None:
            results = [e for e in results if e.category == category]
        if echelon is not None:
            results = [e for e in results if e.echelon == echelon]
        if state is not None:
            results = [e for e in results if e.state == state]
        if effector_type is not None:
            results = [e for e in results if e.effector_type == effector_type]
        if zone_id is not None:
            results = [e for e in results if e.assigned_zone_id == zone_id]
        if available_only:
            results = [e for e in results if e.is_available]
        return results

    def get_available_for_target(
        self,
        target_position: tuple,
        target_speed_mps: float = 0.0,
    ) -> List[Effector]:
        """Return all effectors that can geometrically engage a given target."""
        with self._lock:
            candidates = [
                e
                for e in self._effectors.values()
                if e.can_engage(target_position, target_speed_mps)
            ]
        return sorted(candidates, key=lambda e: e.readiness_score, reverse=True)

    def update_state(self, effector_id: str, new_state: EffectorState) -> bool:
        """Update effector operational state."""
        with self._lock:
            eff = self._effectors.get(effector_id)
            if eff is None:
                return False
            eff.state = new_state
            return True

    def resupply(self, effector_id: str, rounds: Optional[int] = None) -> bool:
        """Resupply ammunition to an effector."""
        with self._lock:
            eff = self._effectors.get(effector_id)
            if eff is None:
                return False
            eff.ammunition_remaining = (
                rounds if rounds is not None else eff.ammunition_total
            )
            if eff.state == EffectorState.RELOADING:
                eff.state = EffectorState.READY
            return True

    def get_stats(self) -> Dict[str, int]:
        """Return summary statistics of the effector inventory."""
        with self._lock:
            effectors = list(self._effectors.values())
        return {
            "total": len(effectors),
            "ready": sum(1 for e in effectors if e.state == EffectorState.READY),
            "engaging": sum(1 for e in effectors if e.state == EffectorState.ENGAGING),
            "reloading": sum(1 for e in effectors if e.state == EffectorState.RELOADING),
            "degraded": sum(1 for e in effectors if e.state == EffectorState.DEGRADED),
            "offline": sum(1 for e in effectors if e.state == EffectorState.OFFLINE),
            "available": sum(1 for e in effectors if e.is_available),
            "total_ammo": sum(e.ammunition_remaining for e in effectors),
        }

    def count(self) -> int:
        with self._lock:
            return len(self._effectors)
