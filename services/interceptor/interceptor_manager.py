"""Fleet-level interceptor management bridging guidance to autopilot and air defense.

Military context:
Manages multiple simultaneous interceptions, each with its own GuidanceComputer.
Bridges between the air defense TargetAllocator (which assigns interceptor drones
to targets), the radar-fused track picture (which provides target state), and the
AutopilotBridge (which commands the physical drone).
"""

from __future__ import annotations

import threading
from typing import Any, Dict, List, Optional, Tuple

from services.interceptor.guidance_computer import GuidanceComputer
from services.interceptor.models import (
    GuidanceSolution,
    InterceptorConfig,
    InterceptResult,
)


class InterceptorManager:
    """Manage fleet of interceptor drones and their active interceptions."""

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._interceptors: Dict[str, InterceptorConfig] = {}
        self._guidance_computers: Dict[str, GuidanceComputer] = {}
        self._results: List[InterceptResult] = []
        self._recorded_result_gc_ids: set[int] = set()

    def register_interceptor(self, config: InterceptorConfig) -> InterceptorConfig:
        """Register an interceptor drone in the fleet."""
        with self._lock:
            self._interceptors[config.interceptor_id] = config
        return config

    def assign_target(self, interceptor_id: str, target_id: str) -> bool:
        """Assign a target and initialize guidance computer."""
        if not interceptor_id or not target_id:
            return False
        with self._lock:
            config = self._interceptors.get(interceptor_id)
            if config is None:
                return False
            gc = GuidanceComputer(config, target_id)
            self._guidance_computers[interceptor_id] = gc
            return True

    def launch(self, interceptor_id: str) -> bool:
        """Launch the interceptor drone."""
        with self._lock:
            gc = self._guidance_computers.get(interceptor_id)
            if gc is None:
                return False
            gc.launch()
            return True

    def radar_acquired(self, interceptor_id: str) -> bool:
        """Mark interceptor as acquired on radar."""
        with self._lock:
            gc = self._guidance_computers.get(interceptor_id)
            if gc is None:
                return False
            gc.radar_acquired()
            return True

    def guide(
        self,
        interceptor_id: str,
        interceptor_pos: Tuple[float, float, float],
        interceptor_vel: Tuple[float, float, float],
        target_pos: Tuple[float, float, float],
        target_vel: Tuple[float, float, float],
    ) -> Optional[GuidanceSolution]:
        """Run one guidance cycle for an active interception."""
        with self._lock:
            gc = self._guidance_computers.get(interceptor_id)
            if gc is None or not gc.is_active:
                return None
            return gc.update(interceptor_pos, interceptor_vel, target_pos, target_vel)

    def get_result(self, interceptor_id: str) -> Optional[InterceptResult]:
        """Fetch current or terminal result for the interceptor."""
        with self._lock:
            gc = self._guidance_computers.get(interceptor_id)
            if gc is None:
                return None
            result = gc.get_result()
            if gc.phase_manager.is_complete:
                gc_id = id(gc)
                if gc_id not in self._recorded_result_gc_ids:
                    # Tactical metrics must count each completed interception once.
                    self._results.append(result)
                    self._recorded_result_gc_ids.add(gc_id)
            return result

    def get_active_interceptions(self) -> List[Dict[str, Any]]:
        with self._lock:
            return [
                {
                    "interceptor_id": iid,
                    "target_id": gc.target_id,
                    "state": gc.current_state.value,
                    "phase": gc.current_phase.value,
                    "cycle": gc._cycle,
                }
                for iid, gc in self._guidance_computers.items()
                if gc.is_active
            ]

    def get_stats(self) -> Dict[str, Any]:
        with self._lock:
            return {
                "registered": len(self._interceptors),
                "active_interceptions": sum(
                    1 for gc in self._guidance_computers.values() if gc.is_active
                ),
                "completed": len(self._results),
                "hits": sum(1 for r in self._results if r.outcome == "hit"),
                "misses": sum(1 for r in self._results if r.outcome == "miss"),
            }
