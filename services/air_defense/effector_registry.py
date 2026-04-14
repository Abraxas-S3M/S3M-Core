"""In-memory effector registry for air defense force templates.

Military context:
Registries provide stable identifiers so tactical planners can reference,
assign, and audit each launcher/sensor node across layered defense zones.
"""

from __future__ import annotations

from typing import Dict, List, Optional

from services.air_defense.models import Effector


class EffectorRegistry:
    """Store and retrieve tactical effectors by stable ID."""

    def __init__(self) -> None:
        self._effectors: Dict[str, Effector] = {}

    def register(self, effector: Effector) -> Effector:
        """Register one effector and reject duplicate IDs."""
        if effector.effector_id in self._effectors:
            raise ValueError(f"effector already registered: {effector.effector_id}")
        self._effectors[effector.effector_id] = effector
        return effector

    def get(self, effector_id: str) -> Optional[Effector]:
        """Fetch one effector by ID."""
        return self._effectors.get(effector_id)

    def list_all(self) -> List[Effector]:
        """Return all known effectors in insertion order."""
        return list(self._effectors.values())
