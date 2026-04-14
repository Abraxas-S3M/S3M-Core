"""Interceptor guidance-phase state machine.

Military context:
Enforces doctrinal transition order from launch to handoff so command guidance
does not prematurely release to autonomous terminal seekers.
"""

from __future__ import annotations

from threading import RLock
from typing import Tuple

from services.interceptor.models import GuidancePhase, InterceptorConfig, InterceptorState


class GuidancePhaseManager:
    """Manage one interceptor lifecycle through guidance phases."""

    def __init__(self, config: InterceptorConfig) -> None:
        self._config = config
        self._lock = RLock()
        self._state = InterceptorState.PRELAUNCH
        self._phase = GuidancePhase.PRELAUNCH
        self._last_range_m: float | None = None

    def reset(self) -> None:
        with self._lock:
            self._state = InterceptorState.PRELAUNCH
            self._phase = GuidancePhase.PRELAUNCH
            self._last_range_m = None

    def get_state(self) -> Tuple[InterceptorState, GuidancePhase]:
        with self._lock:
            return self._state, self._phase

    def _sync_phase_from_state(self) -> None:
        mapping = {
            InterceptorState.PRELAUNCH: GuidancePhase.PRELAUNCH,
            InterceptorState.LAUNCHED: GuidancePhase.PRELAUNCH,
            InterceptorState.RADAR_ACQUIRED: GuidancePhase.MIDCOURSE_GUIDED,
            InterceptorState.MIDCOURSE_GUIDED: GuidancePhase.MIDCOURSE_GUIDED,
            InterceptorState.TERMINAL_APPROACH: GuidancePhase.TERMINAL_APPROACH,
            InterceptorState.AUTONOMOUS_HANDOFF: GuidancePhase.AUTONOMOUS_HANDOFF,
            InterceptorState.ENGAGED: GuidancePhase.ENGAGED,
            InterceptorState.MISS: GuidancePhase.MISS,
            InterceptorState.ABORTED: GuidancePhase.MISS,
        }
        self._phase = mapping[self._state]

    def advance(
        self,
        range_to_target_m: float,
        *,
        launched: bool,
        radar_acquired: bool,
        autonomous_handoff_confirmed: bool,
        engaged: bool,
        abort_recommended: bool,
    ) -> Tuple[InterceptorState, GuidancePhase, str]:
        """Advance state machine according to engagement geometry."""
        with self._lock:
            reason = "state_held"
            if abort_recommended and self._state not in {InterceptorState.ENGAGED, InterceptorState.MISS}:
                self._state = InterceptorState.MISS
                self._sync_phase_from_state()
                self._last_range_m = range_to_target_m
                return self._state, self._phase, "abort_due_to_predicted_miss"

            if engaged and range_to_target_m <= self._config.autonomous_engagement_range_m:
                self._state = InterceptorState.ENGAGED
                self._sync_phase_from_state()
                self._last_range_m = range_to_target_m
                return self._state, self._phase, "engagement_range_reached"

            if self._state == InterceptorState.PRELAUNCH and launched:
                self._state = InterceptorState.LAUNCHED
                reason = "launch_confirmed"

            if self._state == InterceptorState.LAUNCHED and radar_acquired:
                self._state = InterceptorState.RADAR_ACQUIRED
                reason = "radar_acquisition_confirmed"

            if self._state == InterceptorState.RADAR_ACQUIRED:
                self._state = InterceptorState.MIDCOURSE_GUIDED
                reason = "midcourse_guidance_started"

            if self._state == InterceptorState.MIDCOURSE_GUIDED:
                if range_to_target_m <= self._config.terminal_approach_range_m:
                    self._state = InterceptorState.TERMINAL_APPROACH
                    reason = "entered_terminal_approach_window"

            if self._state == InterceptorState.TERMINAL_APPROACH:
                handoff = self._config.handoff_criteria
                if handoff.min_range_m <= range_to_target_m <= handoff.max_range_m:
                    self._state = InterceptorState.AUTONOMOUS_HANDOFF
                    reason = "entered_autonomous_handoff_window"

            if self._state == InterceptorState.AUTONOMOUS_HANDOFF:
                if autonomous_handoff_confirmed:
                    reason = "autonomous_handoff_confirmed"
                elif range_to_target_m > self._config.handoff_criteria.max_range_m:
                    # Tactical recovery: if geometry opens back up, return to terminal command guidance.
                    self._state = InterceptorState.TERMINAL_APPROACH
                    reason = "handoff_window_lost_reverting_terminal"

            if (
                self._last_range_m is not None
                and self._state in {InterceptorState.MIDCOURSE_GUIDED, InterceptorState.TERMINAL_APPROACH}
                and range_to_target_m > self._last_range_m + self._config.miss_abort_distance_m
            ):
                self._state = InterceptorState.MISS
                reason = "range_diverging_declared_miss"

            self._sync_phase_from_state()
            self._last_range_m = range_to_target_m
            return self._state, self._phase, reason
