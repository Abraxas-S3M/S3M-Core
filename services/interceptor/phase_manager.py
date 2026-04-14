"""Guidance phase state machine for active interceptions.

Military context:
Manages transitions from launch to command guidance, terminal homing, and
post-engagement disposition to keep tactical control deterministic.
"""

from __future__ import annotations

from services.interceptor.models import GuidancePhase, HandoffConfig, InterceptGeometry, InterceptorState


class GuidancePhaseManager:
    """Finite-state manager for interceptor engagement phases."""

    def __init__(self, handoff: HandoffConfig) -> None:
        self.handoff = handoff
        self.phase = GuidancePhase.PRE_LAUNCH
        self.state = InterceptorState.READY
        self.abort_reason = ""

    def reset(self) -> None:
        self.phase = GuidancePhase.PRE_LAUNCH
        self.state = InterceptorState.READY
        self.abort_reason = ""

    def launch(self) -> None:
        if self.state is InterceptorState.READY:
            self.phase = GuidancePhase.BOOST
            self.state = InterceptorState.LAUNCHED

    def radar_acquired(self) -> None:
        if self.phase in (GuidancePhase.BOOST, GuidancePhase.MIDCOURSE):
            self.phase = GuidancePhase.MIDCOURSE
            self.state = InterceptorState.GUIDING

    def update(self, geometry: InterceptGeometry) -> InterceptorState:
        if self.is_complete:
            return self.state

        if self.phase == GuidancePhase.PRE_LAUNCH:
            return self.state

        if geometry.range_m <= self.handoff.hit_radius_m:
            self.phase = GuidancePhase.POST_ENGAGE
            self.state = InterceptorState.ENGAGED
            return self.state

        # Tactical context: opening geometry at large slant range usually means
        # command-guided intercept is no longer kinematically viable.
        if geometry.closing_speed_mps <= 0.0 and geometry.range_m > self.handoff.terminal_range_m:
            self.phase = GuidancePhase.POST_ENGAGE
            self.state = InterceptorState.MISS
            self.abort_reason = "target opening range beyond terminal basket"
            return self.state

        if self.handoff.enable_autonomous and geometry.range_m <= self.handoff.max_handoff_range_m:
            self.phase = GuidancePhase.AUTONOMOUS
            self.state = InterceptorState.GUIDING
            return self.state

        if geometry.range_m <= self.handoff.terminal_range_m:
            self.phase = GuidancePhase.TERMINAL
            self.state = InterceptorState.GUIDING
            return self.state

        if self.phase != GuidancePhase.BOOST:
            self.phase = GuidancePhase.MIDCOURSE
        if self.state == InterceptorState.LAUNCHED:
            self.state = InterceptorState.GUIDING
        return self.state

    @property
    def is_guided(self) -> bool:
        return self.phase in (
            GuidancePhase.BOOST,
            GuidancePhase.MIDCOURSE,
            GuidancePhase.TERMINAL,
        )

    @property
    def is_complete(self) -> bool:
        return self.state in (InterceptorState.ENGAGED, InterceptorState.MISS, InterceptorState.LOST)
