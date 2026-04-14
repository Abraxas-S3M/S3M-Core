"""Main interceptor guidance loop (Krechet 9C905-2 equivalent)."""

from __future__ import annotations

from threading import RLock
from typing import Tuple

from services.interceptor.geometry import compute_intercept_geometry
from services.interceptor.guidance_laws import compute_guidance_command
from services.interceptor.models import (
    GuidanceMode,
    GuidancePhase,
    GuidanceSolution,
    InterceptGeometry,
    InterceptorConfig,
    InterceptorState,
    SteeringCommand,
)
from services.interceptor.phase_manager import GuidancePhaseManager

Vector3 = Tuple[float, float, float]


class InterceptorGuidanceComputer:
    """Compute real-time steering commands from interceptor and target states."""

    def __init__(self, interceptor_id: str, config: InterceptorConfig) -> None:
        if not interceptor_id:
            raise ValueError("interceptor_id is required")
        self.interceptor_id = interceptor_id
        self.config = config
        self._lock = RLock()
        self._phase_manager = GuidancePhaseManager(config=config)

    def reset(self) -> None:
        with self._lock:
            self._phase_manager.reset()

    def get_state(self) -> tuple[InterceptorState, GuidancePhase]:
        return self._phase_manager.get_state()

    def _select_mode(self, phase: GuidancePhase) -> GuidanceMode:
        if phase == GuidancePhase.MIDCOURSE_GUIDED:
            return self.config.preferred_mode
        if phase == GuidancePhase.TERMINAL_APPROACH:
            return GuidanceMode.LEAD_PURSUIT
        if phase == GuidancePhase.AUTONOMOUS_HANDOFF:
            return GuidanceMode.PURE_PURSUIT
        return GuidanceMode.PURE_PURSUIT

    def _build_hold_command(self) -> SteeringCommand:
        return SteeringCommand(
            acceleration_mps2=(0.0, 0.0, 0.0),
            desired_velocity_mps=(0.0, 0.0, 0.0),
            commanded_heading_deg=0.0,
            commanded_pitch_deg=0.0,
            throttle_fraction=0.0,
            mode=GuidanceMode.PURE_PURSUIT,
            metadata={"tactical_reason": "no_guidance_command"},
        )

    def _evaluate_handoff_window(self, geometry: InterceptGeometry) -> bool:
        criteria = self.config.handoff_criteria
        return (
            criteria.min_range_m <= geometry.range_m <= criteria.max_range_m
            and geometry.closing_velocity_mps >= criteria.min_closing_velocity_mps
            and geometry.line_of_sight_rate_rad_s <= criteria.max_line_of_sight_rate_rad_s
        )

    def _evaluate_abort(self, geometry: InterceptGeometry) -> bool:
        return (
            geometry.predicted_miss_distance_m > self.config.miss_abort_distance_m
            and geometry.closing_velocity_mps <= 0.0
        )

    def compute_solution(
        self,
        *,
        target_id: str,
        interceptor_position_m: Vector3,
        interceptor_velocity_mps: Vector3,
        target_position_m: Vector3,
        target_velocity_mps: Vector3,
        launched: bool = True,
        radar_acquired: bool = True,
        autonomous_handoff_confirmed: bool = False,
        engaged: bool = False,
        dt_s: float | None = None,
    ) -> GuidanceSolution:
        """Compute one guidance update, including phase transition and steering."""
        with self._lock:
            cycle_dt_s = dt_s if dt_s is not None else 1.0 / self.config.update_rate_hz
            geometry = compute_intercept_geometry(
                interceptor_position_m=interceptor_position_m,
                interceptor_velocity_mps=interceptor_velocity_mps,
                target_position_m=target_position_m,
                target_velocity_mps=target_velocity_mps,
                interceptor_max_speed_mps=self.config.max_speed_mps,
            )

            abort_recommended = self._evaluate_abort(geometry)
            engaged_now = engaged or (geometry.range_m <= self.config.autonomous_engagement_range_m)
            state, phase, transition_reason = self._phase_manager.advance(
                geometry.range_m,
                launched=launched,
                radar_acquired=radar_acquired,
                autonomous_handoff_confirmed=autonomous_handoff_confirmed,
                engaged=engaged_now,
                abort_recommended=abort_recommended,
            )

            handoff_recommended = self._evaluate_handoff_window(geometry)
            mode = self._select_mode(phase)
            if phase in {GuidancePhase.PRELAUNCH, GuidancePhase.ENGAGED, GuidancePhase.MISS}:
                steering = self._build_hold_command()
                if phase == GuidancePhase.ENGAGED:
                    transition_reason = "terminal_engagement_complete"
                if phase == GuidancePhase.MISS:
                    transition_reason = "intercept_miss_declared"
            else:
                steering = compute_guidance_command(
                    mode=mode,
                    interceptor_velocity_mps=interceptor_velocity_mps,
                    target_velocity_mps=target_velocity_mps,
                    geometry=geometry,
                    config=self.config,
                    dt_s=cycle_dt_s,
                )

            if state == InterceptorState.AUTONOMOUS_HANDOFF and handoff_recommended:
                transition_reason = "handoff_window_stable_ready_for_terminal_autonomy"

            return GuidanceSolution(
                interceptor_id=self.interceptor_id,
                target_id=target_id,
                phase=phase,
                mode=steering.mode,
                geometry=geometry,
                steering_command=steering,
                handoff_recommended=handoff_recommended,
                abort_recommended=abort_recommended,
                reason=transition_reason,
            )
