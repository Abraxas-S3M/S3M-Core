"""Guidance phase state machine for interceptor lifecycle.

Military context:
The Krechet 9C905-2 manages each interception through distinct phases:
launch -> radar acquisition -> midcourse guidance -> terminal approach ->
autonomous handoff (200-300m) -> engagement. Each phase has different
guidance behavior and transition criteria.
"""

from __future__ import annotations

from typing import Optional

from services.interceptor.models import (
    GuidancePhase,
    HandoffCriteria,
    InterceptGeometry,
    InterceptorState,
)


class GuidancePhaseManager:
    """Manage guidance phase transitions based on intercept geometry."""

    def __init__(self, handoff: Optional[HandoffCriteria] = None) -> None:
        self.handoff = handoff or HandoffCriteria()
        self.state = InterceptorState.PRELAUNCH
        self.phase = GuidancePhase.BOOST
        self._boost_complete = False
        self._abort_reason = ""

    def reset(self) -> None:
        self.state = InterceptorState.PRELAUNCH
        self.phase = GuidancePhase.BOOST
        self._boost_complete = False
        self._abort_reason = ""

    @property
    def abort_reason(self) -> str:
        return self._abort_reason

    def launch(self) -> None:
        """Transition from PRELAUNCH to LAUNCHED."""
        if self.state == InterceptorState.PRELAUNCH:
            self.state = InterceptorState.LAUNCHED
            self.phase = GuidancePhase.BOOST

    def radar_acquired(self) -> None:
        """Mark interceptor as tracked on radar."""
        if self.state == InterceptorState.LAUNCHED:
            self.state = InterceptorState.RADAR_ACQUIRED
        self._boost_complete = True

    def update(self, geometry: InterceptGeometry) -> InterceptorState:
        """Evaluate current geometry and transition phases.

        Phase transitions:
        - BOOST -> MIDCOURSE: when boost complete and radar acquired
        - MIDCOURSE -> TERMINAL: when range < terminal_range_m (500m default)
        - TERMINAL -> AUTONOMOUS_HANDOFF: when range < handoff_range_m (250m default)
        - Check abort criteria throughout
        """
        if not isinstance(geometry, InterceptGeometry):
            raise TypeError("geometry must be an InterceptGeometry instance")

        # Abort checks (apply in all guided phases)
        if self.state in {
            InterceptorState.MIDCOURSE_GUIDED,
            InterceptorState.TERMINAL_APPROACH,
        }:
            if geometry.closing_velocity_mps < self.handoff.min_closing_velocity_mps:
                if geometry.range_m > self.handoff.terminal_range_m:
                    self._abort_reason = (
                        f"Closing velocity {geometry.closing_velocity_mps:.1f} m/s "
                        f"below minimum {self.handoff.min_closing_velocity_mps:.1f} m/s"
                    )
                    self.state = InterceptorState.MISS
                    self.phase = GuidancePhase.POST_ENGAGE
                    return self.state

            if geometry.predicted_miss_distance_m > self.handoff.max_miss_distance_m:
                if geometry.range_m < self.handoff.terminal_range_m * 2:
                    self._abort_reason = (
                        f"Predicted miss {geometry.predicted_miss_distance_m:.1f}m "
                        f"exceeds limit {self.handoff.max_miss_distance_m:.1f}m"
                    )
                    self.state = InterceptorState.MISS
                    self.phase = GuidancePhase.POST_ENGAGE
                    return self.state

        # Phase transitions
        if self.state == InterceptorState.RADAR_ACQUIRED and self._boost_complete:
            self.state = InterceptorState.MIDCOURSE_GUIDED
            self.phase = GuidancePhase.MIDCOURSE

        if self.state == InterceptorState.MIDCOURSE_GUIDED:
            if geometry.range_m <= self.handoff.terminal_range_m:
                self.state = InterceptorState.TERMINAL_APPROACH
                self.phase = GuidancePhase.TERMINAL

        if self.state == InterceptorState.TERMINAL_APPROACH:
            if geometry.range_m <= self.handoff.handoff_range_m:
                self.state = InterceptorState.AUTONOMOUS_HANDOFF
                self.phase = GuidancePhase.AUTONOMOUS

        if self.state == InterceptorState.AUTONOMOUS_HANDOFF:
            if geometry.range_m <= 10.0:  # Kill radius proximity
                self.state = InterceptorState.ENGAGED
                self.phase = GuidancePhase.POST_ENGAGE

        return self.state

    @property
    def is_guided(self) -> bool:
        """True if C2 should still be computing guidance commands."""
        return self.state in {
            InterceptorState.MIDCOURSE_GUIDED,
            InterceptorState.TERMINAL_APPROACH,
        }

    @property
    def is_terminal(self) -> bool:
        return self.state in {
            InterceptorState.AUTONOMOUS_HANDOFF,
            InterceptorState.ENGAGED,
        }

    @property
    def is_complete(self) -> bool:
        return self.state in {
            InterceptorState.ENGAGED,
            InterceptorState.MISS,
            InterceptorState.LOST,
            InterceptorState.RTB,
        }
