"""In-memory interceptor manager for deterministic guidance control.

Military context:
The manager models a command-post interceptor timeline (assign -> launch ->
radar handoff -> terminal guidance) so offline rehearsals can verify
engagement-state transitions without external dependencies.
"""

from __future__ import annotations

from datetime import datetime, timezone
from math import sqrt
from typing import Any, Dict, List, Optional, Tuple
from uuid import uuid4

from services.interceptor.models import (
    GuidanceSolution,
    InterceptionResult,
    InterceptorConfig,
    InterceptorUnit,
)


def _parse_vec3(raw_value: Any, *, field_name: str) -> Tuple[float, float, float]:
    if not isinstance(raw_value, (tuple, list)) or len(raw_value) != 3:
        raise ValueError(f"{field_name} must be [x_m, y_m, z_m]")
    try:
        x = float(raw_value[0])
        y = float(raw_value[1])
        z = float(raw_value[2])
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{field_name} must contain numeric coordinates") from exc
    return (x, y, z)


def _subtract(a: Tuple[float, float, float], b: Tuple[float, float, float]) -> Tuple[float, float, float]:
    return (a[0] - b[0], a[1] - b[1], a[2] - b[2])


def _dot(a: Tuple[float, float, float], b: Tuple[float, float, float]) -> float:
    return (a[0] * b[0]) + (a[1] * b[1]) + (a[2] * b[2])


class InterceptorManager:
    """Track interceptor state and produce deterministic guidance outputs."""

    def __init__(self) -> None:
        self._interceptors: Dict[str, InterceptorUnit] = {}
        self._engagement_started_at: Dict[str, datetime] = {}
        self._results: Dict[str, InterceptionResult] = {}

        self._register_count = 0
        self._launch_count = 0
        self._guidance_cycles = 0
        self._handoff_count = 0
        self._terminal_count = 0

    def register_interceptor(self, config: InterceptorConfig) -> InterceptorUnit:
        interceptor_id = f"intc-{uuid4().hex[:10]}"
        unit = InterceptorUnit(interceptor_id=interceptor_id, config=config)
        self._interceptors[interceptor_id] = unit
        self._register_count += 1
        return unit

    def assign_target(self, interceptor_id: str, target_id: str) -> bool:
        if not target_id:
            return False
        unit = self._interceptors.get(str(interceptor_id))
        if unit is None:
            return False
        unit.assigned_target_id = str(target_id)
        self._results.pop(unit.interceptor_id, None)
        return True

    def launch(self, interceptor_id: str) -> bool:
        unit = self._interceptors.get(str(interceptor_id))
        if unit is None or not unit.assigned_target_id:
            return False
        if not unit.launched:
            self._launch_count += 1
        unit.launched = True
        self._engagement_started_at[unit.interceptor_id] = datetime.now(timezone.utc)
        return True

    def radar_acquired(self, interceptor_id: str) -> bool:
        unit = self._interceptors.get(str(interceptor_id))
        if unit is None or not unit.launched:
            return False
        unit.radar_acquired = True
        return True

    def guide(
        self,
        interceptor_id: str,
        interceptor_position: Any,
        interceptor_velocity: Any,
        target_position: Any,
        target_velocity: Any,
    ) -> Optional[GuidanceSolution]:
        unit = self._interceptors.get(str(interceptor_id))
        if unit is None or not unit.launched or not unit.assigned_target_id:
            return None

        intc_pos = _parse_vec3(interceptor_position, field_name="interceptor_position")
        intc_vel = _parse_vec3(interceptor_velocity, field_name="interceptor_velocity")
        tgt_pos = _parse_vec3(target_position, field_name="target_position")
        tgt_vel = _parse_vec3(target_velocity, field_name="target_velocity")

        rel_pos = _subtract(tgt_pos, intc_pos)
        rel_vel = _subtract(tgt_vel, intc_vel)
        range_to_target = sqrt(_dot(rel_pos, rel_pos))
        if range_to_target > 1e-6:
            los_hat = (
                rel_pos[0] / range_to_target,
                rel_pos[1] / range_to_target,
                rel_pos[2] / range_to_target,
            )
            closing_speed = max(0.0, -_dot(rel_pos, rel_vel) / range_to_target)
        else:
            los_hat = (0.0, 0.0, 0.0)
            closing_speed = 0.0

        # Tactical note: command vector approximates PN acceleration intent.
        command_gain = unit.config.nav_constant * closing_speed
        command_vector = (
            los_hat[0] * command_gain,
            los_hat[1] * command_gain,
            los_hat[2] * command_gain,
        )

        handoff_initiated = range_to_target <= unit.config.handoff.handoff_range_m
        terminal_phase = unit.radar_acquired and range_to_target <= unit.config.handoff.terminal_range_m
        guidance_mode = "terminal_homing" if terminal_phase else "midcourse_pn"
        if handoff_initiated:
            self._handoff_count += 1
        if terminal_phase:
            self._terminal_count += 1

        self._guidance_cycles += 1
        solution = GuidanceSolution(
            interceptor_id=unit.interceptor_id,
            target_id=unit.assigned_target_id,
            guidance_mode=guidance_mode,
            command_vector_mps2=command_vector,
            range_to_target_m=range_to_target,
            closing_speed_mps=closing_speed,
            handoff_initiated=handoff_initiated,
            terminal_phase=terminal_phase,
        )

        if terminal_phase and range_to_target <= 5.0:
            started_at = self._engagement_started_at.get(unit.interceptor_id)
            now = datetime.now(timezone.utc)
            elapsed = (now - started_at).total_seconds() if started_at is not None else 0.0
            self._results[unit.interceptor_id] = InterceptionResult(
                interceptor_id=unit.interceptor_id,
                target_id=unit.assigned_target_id,
                status="completed",
                outcome="intercepted",
                final_range_m=range_to_target,
                engagement_time_s=elapsed,
            )
            unit.launched = False
            unit.radar_acquired = False
            self._engagement_started_at.pop(unit.interceptor_id, None)

        return solution

    def get_active_interceptions(self) -> List[Dict[str, Any]]:
        active: List[Dict[str, Any]] = []
        for unit in self._interceptors.values():
            if not unit.launched or not unit.assigned_target_id:
                continue
            active.append(
                {
                    "interceptor_id": unit.interceptor_id,
                    "target_id": unit.assigned_target_id,
                    "radar_acquired": unit.radar_acquired,
                    "launched": unit.launched,
                }
            )
        return active

    def get_result(self, interceptor_id: str) -> Optional[InterceptionResult]:
        return self._results.get(str(interceptor_id))

    def get_stats(self) -> Dict[str, Any]:
        active_count = len(self.get_active_interceptions())
        return {
            "interceptors_registered": len(self._interceptors),
            "register_events": self._register_count,
            "launch_events": self._launch_count,
            "guidance_cycles": self._guidance_cycles,
            "handoff_events": self._handoff_count,
            "terminal_events": self._terminal_count,
            "active_interceptions": active_count,
            "completed_interceptions": len(self._results),
        }

