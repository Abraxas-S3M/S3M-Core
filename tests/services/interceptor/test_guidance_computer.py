"""Unit tests for the guidance computer control loop.

Military context:
These tests verify the command-guidance loop transitions correctly from C2
control to autonomous handoff and post-engagement disposition.
"""

from __future__ import annotations

import pytest

from services.interceptor.guidance_computer import GuidanceComputer
from services.interceptor.models import GuidancePhase, InterceptorConfig, InterceptorState, SteeringCommand


def _config() -> InterceptorConfig:
    return InterceptorConfig(interceptor_id="k9c905-2")


def test_update_runs_guided_cycle_after_launch_and_acquisition() -> None:
    computer = GuidanceComputer(config=_config(), target_id="t-1")
    computer.launch()
    computer.radar_acquired()

    solution = computer.update(
        interceptor_pos=(0.0, 0.0, 0.0),
        interceptor_vel=(250.0, 0.0, 0.0),
        target_pos=(1_800.0, 200.0, 50.0),
        target_vel=(-120.0, 0.0, 0.0),
    )

    assert solution.cycle_number == 1
    assert solution.phase in (GuidancePhase.MIDCOURSE, GuidancePhase.TERMINAL)
    assert solution.feasible


def test_terminal_phase_uses_tighter_navigation_constant() -> None:
    computer = GuidanceComputer(config=_config(), target_id="t-2")
    computer.launch()
    computer.radar_acquired()

    captured: dict[str, float] = {}

    class _CapturePN:
        def compute(
            self,
            geometry,
            interceptor_pos,
            interceptor_vel,
            target_pos,
            target_vel,
            config,
            phase,
        ):
            del geometry, interceptor_pos, interceptor_vel, target_pos, target_vel
            captured["nav_constant"] = config.nav_constant
            return SteeringCommand(phase=phase)

    computer.pn_guidance = _CapturePN()  # type: ignore[assignment]
    computer.update(
        interceptor_pos=(0.0, 0.0, 0.0),
        interceptor_vel=(250.0, 0.0, 0.0),
        target_pos=(1_000.0, 40.0, 5.0),  # inside terminal range, above handoff
        target_vel=(-80.0, 0.0, 0.0),
    )

    assert captured["nav_constant"] == pytest.approx(computer.config.nav_constant + 1.0)


def test_update_switches_to_autonomous_inside_handoff_window() -> None:
    computer = GuidanceComputer(config=_config(), target_id="t-3")
    computer.launch()
    computer.radar_acquired()

    solution = computer.update(
        interceptor_pos=(0.0, 0.0, 0.0),
        interceptor_vel=(250.0, 0.0, 0.0),
        target_pos=(280.0, 0.0, 0.0),  # inside max handoff range
        target_vel=(-20.0, 0.0, 0.0),
    )

    assert solution.phase == GuidancePhase.AUTONOMOUS
    assert solution.command.phase == GuidancePhase.AUTONOMOUS
    assert computer.current_state == InterceptorState.GUIDING


def test_update_marks_miss_for_opening_target() -> None:
    computer = GuidanceComputer(config=_config(), target_id="t-4")
    computer.launch()
    computer.radar_acquired()

    solution = computer.update(
        interceptor_pos=(0.0, 0.0, 0.0),
        interceptor_vel=(100.0, 0.0, 0.0),
        target_pos=(4_000.0, 0.0, 0.0),
        target_vel=(400.0, 0.0, 0.0),
    )

    assert solution.state == InterceptorState.MISS
    assert solution.phase == GuidancePhase.POST_ENGAGE
    assert not solution.feasible
    assert solution.abort_reason


def test_update_validates_vector_inputs() -> None:
    computer = GuidanceComputer(config=_config(), target_id="t-5")
    computer.launch()
    computer.radar_acquired()

    with pytest.raises(ValueError):
        computer.update(
            interceptor_pos=(0.0, 0.0, 0.0),
            interceptor_vel=(1.0, 2.0, 3.0),
            target_pos=(100.0, 0.0, 0.0),
            target_vel=(float("nan"), 0.0, 0.0),
        )
