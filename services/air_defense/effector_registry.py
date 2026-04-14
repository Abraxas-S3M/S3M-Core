"""Thread-safe effector registry for tactical air-defense channels.

Military context:
The registry is the authoritative local state for fire units, ensuring
deterministic control of ammunition, readiness, and queue pressure in
air-gapped command posts.
"""

from __future__ import annotations

from dataclasses import replace
from threading import RLock
import time
from typing import Dict, List, Optional, Sequence

from services.air_defense.models import DefenseEchelon, Effector, EffectorCategory, EffectorType


class EffectorRegistry:
    """Thread-safe registry for typed effectors and mutable combat state."""

    def __init__(self) -> None:
        self._lock = RLock()
        self._effectors: Dict[str, Effector] = {}

    def register_effector(self, effector: Effector, *, replace_existing: bool = False) -> Effector:
        """Register an effector object and return the stored instance."""
        with self._lock:
            if effector.effector_id in self._effectors and not replace_existing:
                raise ValueError(f"effector already exists: {effector.effector_id}")
            self._effectors[effector.effector_id] = effector
            return effector

    def remove_effector(self, effector_id: str) -> Optional[Effector]:
        """Remove an effector by ID and return removed object when present."""
        with self._lock:
            return self._effectors.pop(str(effector_id), None)

    def get_effector(self, effector_id: str) -> Optional[Effector]:
        """Return effector by ID, if present."""
        with self._lock:
            return self._effectors.get(str(effector_id))

    def list_effectors(self) -> List[Effector]:
        """Return all effectors sorted by ID for deterministic behavior."""
        with self._lock:
            return [self._effectors[key] for key in sorted(self._effectors.keys())]

    def query_effectors(
        self,
        *,
        effector_type: Optional[EffectorType] = None,
        category: Optional[EffectorCategory] = None,
        echelon: Optional[DefenseEchelon] = None,
        zone_id: Optional[str] = None,
        ready_only: bool = False,
        now_ts: Optional[float] = None,
    ) -> List[Effector]:
        """Filter effectors by tactical attributes and readiness state."""
        with self._lock:
            effectors = list(self._effectors.values())
            if effector_type is not None:
                effectors = [e for e in effectors if e.effector_type == effector_type]
            if category is not None:
                effectors = [e for e in effectors if e.category == category]
            if echelon is not None:
                effectors = [e for e in effectors if e.echelon == echelon]
            if zone_id is not None:
                effectors = [e for e in effectors if e.zone_id == zone_id]
            if ready_only:
                effectors = [e for e in effectors if e.state.is_ready(now_ts=now_ts)]
            return sorted(effectors, key=lambda item: item.effector_id)

    def update_ammunition(self, effector_id: str, ammunition_current: int) -> Effector:
        """Set absolute ammunition count for one effector."""
        with self._lock:
            effector = self._require_effector(effector_id)
            updated = max(0, min(int(ammunition_current), effector.state.ammunition_capacity))
            effector.state.ammunition_current = updated
            if updated == 0 and effector.state.status == "ready":
                effector.state.status = "degraded"
            return effector

    def consume_ammunition(self, effector_id: str, rounds: int = 1) -> bool:
        """Consume rounds; return False when inventory is insufficient."""
        required = max(1, int(rounds))
        with self._lock:
            effector = self._require_effector(effector_id)
            if effector.state.ammunition_current < required:
                return False
            effector.state.ammunition_current -= required
            if effector.state.ammunition_current == 0 and effector.state.status == "ready":
                effector.state.status = "degraded"
            return True

    def set_readiness(self, effector_id: str, readiness: float, *, status: Optional[str] = None) -> Effector:
        """Update readiness score and optionally explicit status."""
        with self._lock:
            effector = self._require_effector(effector_id)
            effector.state.readiness = max(0.0, min(1.0, float(readiness)))
            if status is not None:
                normalized = str(status).strip().lower()
                if normalized not in {"ready", "degraded", "reloading", "offline", "maintenance"}:
                    raise ValueError("invalid readiness status")
                effector.state.status = normalized
            elif effector.state.readiness < 0.5 and effector.state.status == "ready":
                effector.state.status = "degraded"
            return effector

    def record_shot(self, effector_id: str, *, timestamp: Optional[float] = None) -> Effector:
        """Mark firing time to enforce reload windows."""
        with self._lock:
            effector = self._require_effector(effector_id)
            shot_ts = time.time() if timestamp is None else float(timestamp)
            effector.state.last_fired_timestamp = shot_ts
            if effector.state.reload_time_seconds > 0 and effector.state.status in {"ready", "degraded"}:
                effector.state.status = "reloading"
            return effector

    def refresh_reload_state(self, effector_id: str, *, now_ts: Optional[float] = None) -> Effector:
        """Promote a reloading channel back to ready/degraded when complete."""
        with self._lock:
            effector = self._require_effector(effector_id)
            now = time.time() if now_ts is None else float(now_ts)
            if effector.state.status == "reloading" and effector.state.reload_complete(now_ts=now):
                effector.state.status = "ready" if effector.state.readiness >= 0.5 else "degraded"
            return effector

    def enqueue_target(self, effector_id: str) -> int:
        """Increment queue depth and return resulting queue index."""
        with self._lock:
            effector = self._require_effector(effector_id)
            effector.state.queued_targets += 1
            return effector.state.queued_targets

    def dequeue_target(self, effector_id: str) -> int:
        """Decrement queue depth safely and return resulting queue size."""
        with self._lock:
            effector = self._require_effector(effector_id)
            effector.state.queued_targets = max(0, effector.state.queued_targets - 1)
            return effector.state.queued_targets

    def queue_depth(self, effector_id: str) -> int:
        """Return current queue depth for an effector."""
        with self._lock:
            return self._require_effector(effector_id).state.queued_targets

    def snapshot(self) -> Dict[str, Effector]:
        """Return deterministic copy of current registry state."""
        with self._lock:
            return {key: replace(value) for key, value in sorted(self._effectors.items(), key=lambda kv: kv[0])}

    def _require_effector(self, effector_id: str) -> Effector:
        key = str(effector_id)
        effector = self._effectors.get(key)
        if effector is None:
            raise KeyError(f"effector not found: {key}")
        return effector

    def query_by_types(self, types: Sequence[EffectorType]) -> List[Effector]:
        """Return effectors matching any provided type."""
        type_set = set(types)
        if not type_set:
            return []
        with self._lock:
            return sorted(
                [effector for effector in self._effectors.values() if effector.effector_type in type_set],
                key=lambda item: item.effector_id,
            )
