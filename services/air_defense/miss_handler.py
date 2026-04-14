"""Miss and kill handling for air-defense engagement lifecycle.

Military context:
Miss processing captures engagement failure evidence and triggers immediate
re-tasking so operators can sustain defensive pressure on inbound threats.
"""

from __future__ import annotations

from collections import Counter
from datetime import datetime, timezone
from typing import Dict, List, Optional, Tuple

from services.air_defense.effector_registry import EffectorRegistry
from services.air_defense.models import AllocationDecision, AllocationRecord, EffectorState
from services.air_defense.target_allocator import TargetAllocator


class MissHandler:
    """Handle miss reports, re-allocation, and engagement outcome metrics."""

    def __init__(self, registry: EffectorRegistry, allocator: TargetAllocator) -> None:
        self.registry = registry
        self.allocator = allocator
        self._miss_log: List[Dict[str, object]] = []
        self._kill_log: List[Dict[str, object]] = []

    def report_miss(
        self,
        allocation: AllocationRecord,
        updated_position: Optional[Tuple[float, float, float]],
        updated_speed: Optional[float],
    ) -> AllocationDecision:
        """Record miss and attempt immediate reallocation."""
        self.registry.update_state(allocation.effector_id, EffectorState.READY)
        new_position = updated_position if updated_position is not None else allocation.target_position
        new_speed = float(updated_speed) if updated_speed is not None else float(allocation.target_speed_mps)
        self._miss_log.append(
            {
                "allocation_id": allocation.allocation_id,
                "target_id": allocation.target_id,
                "effector_id": allocation.effector_id,
                "updated_position": list(new_position),
                "updated_speed": new_speed,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }
        )
        return self.allocator.allocate(
            allocation.target_id,
            new_position,
            new_speed,
            allocation.classification,
        )

    def report_kill(self, allocation: AllocationRecord) -> None:
        """Record confirmed target neutralization."""
        self.registry.update_state(allocation.effector_id, EffectorState.READY)
        self._kill_log.append(
            {
                "allocation_id": allocation.allocation_id,
                "target_id": allocation.target_id,
                "effector_id": allocation.effector_id,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }
        )

    def get_miss_log(self, limit: int = 100) -> List[Dict[str, object]]:
        """Return most recent miss events for operator review."""
        safe_limit = max(1, min(int(limit), 10_000))
        return list(reversed(self._miss_log[-safe_limit:]))

    def get_miss_stats(self) -> Dict[str, object]:
        """Return aggregate miss/kill metrics for tactical dashboards."""
        misses_by_effector = Counter(str(entry.get("effector_id", "")) for entry in self._miss_log)
        kills_by_effector = Counter(str(entry.get("effector_id", "")) for entry in self._kill_log)
        return {
            "misses_total": len(self._miss_log),
            "kills_total": len(self._kill_log),
            "misses_by_effector": dict(misses_by_effector),
            "kills_by_effector": dict(kills_by_effector),
        }

