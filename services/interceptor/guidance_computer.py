"""Main guidance computer - the Krechet 9C905-2 equivalent.

Military context:
This is the core computational engine that the Krechet 9C905-2 terminal runs
for each active interception. Every guidance cycle it:
1. Receives updated target state from fused radar picture
2. Receives interceptor state (position, velocity from radar tracking)
3. Computes intercept geometry
4. Selects and runs appropriate guidance law
5. Outputs steering command
6. Manages phase transitions
7. Decides handoff to autonomous terminal guidance at 200-300m
"""

from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timezone
from math import isfinite
from typing import List, Optional, Tuple

from services.interceptor.geometry import InterceptGeometryComputer
from services.interceptor.guidance_laws import LeadPursuit, ProportionalNavigation, PurePursuit
from services.interceptor.models import (
    GuidanceMode,
    GuidancePhase,
    GuidanceSolution,
    InterceptorConfig,
    InterceptorState,
    InterceptResult,
    SteeringCommand,
)
from services.interceptor.phase_manager import GuidancePhaseManager


def _validate_vector_input(
    value: Tuple[float, float, float],
    *,
    field_name: str,
) -> Tuple[float, float, float]:
    if len(value) != 3:
        raise ValueError(f"{field_name} must contain exactly three coordinates")
    x, y, z = float(value[0]), float(value[1]), float(value[2])
    if not (isfinite(x) and isfinite(y) and isfinite(z)):
        raise ValueError(f"{field_name} coordinates must be finite numbers")
    return (x, y, z)


class GuidanceComputer:
    """Real-time interceptor guidance computation engine.

    One GuidanceComputer instance manages one active interception.
    For multiple simultaneous interceptions, create multiple instances
    (the InterceptorManager handles this).
    """

    def __init__(self, config: InterceptorConfig, target_id: str = "") -> None:
        self.config = config
        self.target_id = target_id
        self.geometry_computer = InterceptGeometryComputer()
        self.phase_manager = GuidancePhaseManager(config.handoff)

        # Guidance law instances
        self.pure_pursuit = PurePursuit()
        self.lead_pursuit = LeadPursuit()
        self.pn_guidance = ProportionalNavigation()

        # Active guidance mode (PN is default, matching Krechet)
        self.active_mode = GuidanceMode.PROPORTIONAL_NAV

        # State tracking
        self._cycle = 0
        self._solutions: List[GuidanceSolution] = []
        self._start_time: Optional[datetime] = None
        self._last_interceptor_pos: Optional[Tuple[float, float, float]] = None
        self._last_interceptor_vel: Optional[Tuple[float, float, float]] = None

    def reset(self, target_id: str = "") -> None:
        """Reset for new interception."""
        self.target_id = target_id
        self.geometry_computer.reset()
        self.phase_manager.reset()
        self._cycle = 0
        self._solutions.clear()
        self._start_time = None
        self._last_interceptor_pos = None
        self._last_interceptor_vel = None

    def launch(self) -> None:
        """Mark interceptor as launched."""
        self.phase_manager.launch()
        self._start_time = datetime.now(timezone.utc)

    def radar_acquired(self) -> None:
        """Mark interceptor as acquired on radar and ready for guidance."""
        self.phase_manager.radar_acquired()

    def update(
        self,
        interceptor_pos: Tuple[float, float, float],
        interceptor_vel: Tuple[float, float, float],
        target_pos: Tuple[float, float, float],
        target_vel: Tuple[float, float, float],
    ) -> GuidanceSolution:
        """Run one guidance cycle.

        This is the method called at guidance_update_hz rate (typically 10 Hz).
        It implements the Krechet 9C905-2 guidance loop.
        """
        interceptor_pos = _validate_vector_input(interceptor_pos, field_name="interceptor_pos")
        interceptor_vel = _validate_vector_input(interceptor_vel, field_name="interceptor_vel")
        target_pos = _validate_vector_input(target_pos, field_name="target_pos")
        target_vel = _validate_vector_input(target_vel, field_name="target_vel")

        self._cycle += 1
        self._last_interceptor_pos = interceptor_pos
        self._last_interceptor_vel = interceptor_vel
        time_s = self._cycle / max(self.config.guidance_update_hz, 1.0)

        # Step 1: Compute geometry
        geometry = self.geometry_computer.compute(
            interceptor_pos, interceptor_vel, target_pos, target_vel, time_s
        )

        # Step 2: Update phase state machine
        state = self.phase_manager.update(geometry)

        # Step 3: Compute steering command (only if still C2-guided)
        if self.phase_manager.is_guided:
            command = self._compute_guidance(
                geometry,
                interceptor_pos,
                interceptor_vel,
                target_pos,
                target_vel,
                self.phase_manager.phase,
            )
            feasible = True
            abort_reason = ""
        elif self.phase_manager.is_complete:
            command = SteeringCommand(phase=GuidancePhase.POST_ENGAGE, notes="engagement complete")
            feasible = state is InterceptorState.ENGAGED
            abort_reason = self.phase_manager.abort_reason
        else:
            # Autonomous phase - command is "maintain heading toward target".
            command = self.pure_pursuit.compute(
                geometry,
                interceptor_pos,
                target_pos,
                self.config,
                GuidancePhase.AUTONOMOUS,
            )
            feasible = True
            abort_reason = ""

        solution = GuidanceSolution(
            interceptor_id=self.config.interceptor_id,
            target_id=self.target_id,
            cycle_number=self._cycle,
            geometry=geometry,
            command=command,
            phase=self.phase_manager.phase,
            state=state,
            feasible=feasible,
            abort_reason=abort_reason,
        )
        self._solutions.append(solution)

        # Keep solution history bounded
        if len(self._solutions) > 1000:
            self._solutions = self._solutions[-500:]

        return solution

    def _compute_guidance(
        self,
        geometry,
        interceptor_pos,
        interceptor_vel,
        target_pos,
        target_vel,
        phase: GuidancePhase,
    ) -> SteeringCommand:
        """Select and execute guidance law based on active mode and phase."""
        config = self.config
        if phase == GuidancePhase.TERMINAL:
            # Tactical context: larger PN constant in terminal phase narrows
            # the endgame miss basket against evasive targets.
            config = replace(self.config, nav_constant=self.config.nav_constant + 1.0)

        if self.active_mode == GuidanceMode.PROPORTIONAL_NAV:
            return self.pn_guidance.compute(
                geometry,
                interceptor_pos,
                interceptor_vel,
                target_pos,
                target_vel,
                config,
                phase,
            )
        if self.active_mode == GuidanceMode.LEAD_PURSUIT:
            return self.lead_pursuit.compute(
                geometry,
                interceptor_pos,
                target_pos,
                target_vel,
                config,
                phase,
            )
        return self.pure_pursuit.compute(
            geometry,
            interceptor_pos,
            target_pos,
            config,
            phase,
        )

    def get_result(self) -> InterceptResult:
        """Produce final interception result."""
        last_solution = self._solutions[-1] if self._solutions else None
        engagement_time = 0.0
        if self._start_time:
            engagement_time = (datetime.now(timezone.utc) - self._start_time).total_seconds()

        outcome = "pending"
        if self.phase_manager.state == InterceptorState.ENGAGED:
            outcome = "hit"
        elif self.phase_manager.state == InterceptorState.MISS:
            outcome = "miss"
        elif self.phase_manager.state == InterceptorState.LOST:
            outcome = "lost_track"

        return InterceptResult(
            interceptor_id=self.config.interceptor_id,
            target_id=self.target_id,
            outcome=outcome,
            miss_distance_m=(
                last_solution.geometry.predicted_miss_distance_m if last_solution else 0.0
            ),
            engagement_time_s=max(engagement_time, 0.0),
            guidance_cycles=self._cycle,
            final_phase=self.phase_manager.phase,
            final_range_m=last_solution.geometry.range_m if last_solution else 0.0,
            abort_reason=self.phase_manager.abort_reason,
        )

    def get_solution_log(self, limit: int = 50) -> List[GuidanceSolution]:
        return self._solutions[-max(0, int(limit)) :]

    @property
    def is_active(self) -> bool:
        return not self.phase_manager.is_complete

    @property
    def current_phase(self) -> GuidancePhase:
        return self.phase_manager.phase

    @property
    def current_state(self) -> InterceptorState:
        return self.phase_manager.state
