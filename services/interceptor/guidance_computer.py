"""Per-interceptor guidance engine for drone-to-target interception.

Military context:
This component executes deterministic local guidance so each interceptor can
continue engagement even during degraded comms with higher-echelon command.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from math import sqrt
from typing import Tuple

from services.interceptor.models import (
    GuidanceSolution,
    InterceptorConfig,
    InterceptorState,
    InterceptResult,
    Vec3,
    _validate_vec3,
)


class GuidancePhase(str, Enum):
    PRE_LAUNCH = "pre_launch"
    BOOST = "boost"
    MIDCOURSE = "midcourse"
    TERMINAL = "terminal"
    COMPLETE = "complete"


@dataclass
class PhaseManager:
    current_phase: GuidancePhase = GuidancePhase.PRE_LAUNCH

    @property
    def is_complete(self) -> bool:
        return self.current_phase is GuidancePhase.COMPLETE

    def set_phase(self, phase: GuidancePhase) -> None:
        self.current_phase = phase


class GuidanceComputer:
    """Compute guidance commands for a single assigned interceptor."""

    def __init__(self, config: InterceptorConfig, target_id: str) -> None:
        if not target_id:
            raise ValueError("target_id is required")
        self.config = config
        self.target_id = target_id
        self.phase_manager = PhaseManager()
        self.current_state = InterceptorState.ASSIGNED
        self.current_phase = self.phase_manager.current_phase
        self._cycle = 0
        self._radar_locked = False
        self._last_range_m = float("inf")
        self._result: InterceptResult | None = None

    @property
    def is_active(self) -> bool:
        return self.current_state is not InterceptorState.COMPLETE

    def launch(self) -> None:
        if self.phase_manager.is_complete:
            return
        self.current_state = InterceptorState.LAUNCHED
        self.phase_manager.set_phase(GuidancePhase.BOOST)
        self.current_phase = self.phase_manager.current_phase

    def radar_acquired(self) -> None:
        if self.phase_manager.is_complete:
            return
        self._radar_locked = True
        if self.current_state in {InterceptorState.LAUNCHED, InterceptorState.ASSIGNED}:
            self.current_state = InterceptorState.TRACKING
            self.phase_manager.set_phase(GuidancePhase.MIDCOURSE)
            self.current_phase = self.phase_manager.current_phase

    def update(
        self,
        interceptor_pos: Tuple[float, float, float],
        interceptor_vel: Tuple[float, float, float],
        target_pos: Tuple[float, float, float],
        target_vel: Tuple[float, float, float],
    ) -> GuidanceSolution:
        if self.phase_manager.is_complete:
            raise RuntimeError("guidance update called after engagement completion")

        i_pos = _validate_vec3(interceptor_pos, field_name="interceptor_pos")
        i_vel = _validate_vec3(interceptor_vel, field_name="interceptor_vel")
        t_pos = _validate_vec3(target_pos, field_name="target_pos")
        t_vel = _validate_vec3(target_vel, field_name="target_vel")

        self._cycle += 1
        rel = (t_pos[0] - i_pos[0], t_pos[1] - i_pos[1], t_pos[2] - i_pos[2])
        rel_vel = (t_vel[0] - i_vel[0], t_vel[1] - i_vel[1], t_vel[2] - i_vel[2])
        range_to_target_m = sqrt(rel[0] ** 2 + rel[1] ** 2 + rel[2] ** 2)
        self._last_range_m = range_to_target_m

        if range_to_target_m > 0.0:
            closing_speed_mps = -(
                (rel[0] * rel_vel[0] + rel[1] * rel_vel[1] + rel[2] * rel_vel[2])
                / range_to_target_m
            )
            unit_los = (rel[0] / range_to_target_m, rel[1] / range_to_target_m, rel[2] / range_to_target_m)
        else:
            closing_speed_mps = self.config.max_speed_mps
            unit_los = (0.0, 0.0, 0.0)

        accel = self._scaled_vec(unit_los, self.config.max_acceleration_mps2)

        if range_to_target_m <= self.config.hit_radius_m:
            self._complete(outcome="hit", final_range_m=range_to_target_m)
            should_fire_fuze = True
        elif self._cycle >= int(self.config.fuel_endurance_s):
            self._complete(outcome="miss", final_range_m=range_to_target_m)
            should_fire_fuze = False
        else:
            if self._radar_locked and range_to_target_m <= self.config.seeker_acquisition_range_m:
                # Terminal transition indicates local seeker handoff near endgame.
                self.current_state = InterceptorState.TERMINAL
                self.phase_manager.set_phase(GuidancePhase.TERMINAL)
                self.current_phase = self.phase_manager.current_phase
            should_fire_fuze = range_to_target_m <= (self.config.hit_radius_m * 1.5)

        return GuidanceSolution(
            interceptor_id=self.config.interceptor_id,
            target_id=self.target_id,
            interceptor_state=self.current_state,
            command_acceleration_mps2=accel,
            range_to_target_m=range_to_target_m,
            closing_speed_mps=closing_speed_mps,
            should_fire_fuze=should_fire_fuze,
        )

    def get_result(self) -> InterceptResult:
        if self._result is not None:
            return self._result
        final_range = self._last_range_m if self._last_range_m != float("inf") else 0.0
        return InterceptResult(
            interceptor_id=self.config.interceptor_id,
            target_id=self.target_id,
            outcome="incomplete",
            final_state=self.current_state,
            final_range_m=final_range,
            cycles_completed=self._cycle,
        )

    def _complete(self, *, outcome: str, final_range_m: float) -> None:
        self.current_state = InterceptorState.COMPLETE
        self.phase_manager.set_phase(GuidancePhase.COMPLETE)
        self.current_phase = self.phase_manager.current_phase
        self._result = InterceptResult(
            interceptor_id=self.config.interceptor_id,
            target_id=self.target_id,
            outcome=outcome,
            final_state=InterceptorState.COMPLETE,
            final_range_m=final_range_m,
            cycles_completed=self._cycle,
        )

    @staticmethod
    def _scaled_vec(vec: Vec3, magnitude: float) -> Vec3:
        return (vec[0] * magnitude, vec[1] * magnitude, vec[2] * magnitude)
