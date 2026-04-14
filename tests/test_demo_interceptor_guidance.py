"""Unit tests for interceptor guidance demo script."""

from __future__ import annotations

import importlib
import sys
import types
from dataclasses import dataclass
from enum import Enum


def _install_interceptor_stubs(monkeypatch) -> None:
    """Install deterministic tactical interceptor stubs for demo validation."""

    services_pkg = sys.modules.get("services")
    if services_pkg is None:
        services_pkg = types.ModuleType("services")
        services_pkg.__path__ = []
        monkeypatch.setitem(sys.modules, "services", services_pkg)

    interceptor_pkg = types.ModuleType("services.interceptor")
    interceptor_pkg.__path__ = []
    monkeypatch.setitem(sys.modules, "services.interceptor", interceptor_pkg)

    class Phase(Enum):
        MIDCOURSE = "midcourse"
        TERMINAL = "terminal"
        ENDGAME = "endgame"

    class FinalPhase(Enum):
        ENDGAME = "endgame"

    class State(Enum):
        LAUNCHED = "launched"

    @dataclass
    class HandoffCriteria:
        handoff_range_m: float
        terminal_range_m: float

    @dataclass
    class InterceptorConfig:
        name_en: str
        name_ar: str
        platform_type: str
        max_speed_mps: float
        cruise_speed_mps: float
        max_acceleration_mps2: float
        nav_constant: float
        guidance_update_hz: int
        handoff: HandoffCriteria
        kill_radius_m: float

    class GuidanceComputer:
        """Simple deterministic tactical guidance emulator for script testing."""

        def __init__(self, config: InterceptorConfig, target_id: str) -> None:
            self.config = config
            self.target_id = target_id
            self.current_state = State.LAUNCHED
            self.phase_manager = types.SimpleNamespace(is_complete=False)
            self._cycle = 0

        def launch(self) -> None:
            self.current_state = State.LAUNCHED

        def radar_acquired(self) -> None:
            return None

        def update(self, intc_pos, intc_vel, tgt_pos, tgt_vel):
            _ = (intc_pos, intc_vel, tgt_pos, tgt_vel)
            self._cycle += 1
            if self._cycle < 3:
                phase = Phase.MIDCOURSE
            elif self._cycle < 5:
                phase = Phase.TERMINAL
            else:
                phase = Phase.ENDGAME
                self.phase_manager.is_complete = True

            geometry = types.SimpleNamespace(
                range_m=max(0.0, 10000.0 - self._cycle * 2500.0),
                closing_velocity_mps=120.0,
                time_to_intercept_s=max(0.1, 8.0 - self._cycle),
                predicted_miss_distance_m=max(0.0, 40.0 - self._cycle * 10.0),
            )
            command = types.SimpleNamespace(
                commanded_heading_deg=185.0,
                lateral_accel_mps2=2.2,
                commanded_position=(10.0, 20.0, 500.0),
            )
            return types.SimpleNamespace(phase=phase, geometry=geometry, command=command)

        def get_result(self):
            return types.SimpleNamespace(
                outcome="kill",
                miss_distance_m=1.8,
                engagement_time_s=4.2,
                guidance_cycles=self._cycle,
                final_phase=FinalPhase.ENDGAME,
                final_range_m=1.8,
                abort_reason=None,
            )

    models_mod = types.ModuleType("services.interceptor.models")
    models_mod.InterceptorConfig = InterceptorConfig
    models_mod.HandoffCriteria = HandoffCriteria
    monkeypatch.setitem(sys.modules, "services.interceptor.models", models_mod)

    guidance_mod = types.ModuleType("services.interceptor.guidance_computer")
    guidance_mod.GuidanceComputer = GuidanceComputer
    monkeypatch.setitem(sys.modules, "services.interceptor.guidance_computer", guidance_mod)


def test_demo_interceptor_guidance_runs_full_intercept(monkeypatch, capsys) -> None:
    """Demo should progress through guidance phases and print engagement result."""

    _install_interceptor_stubs(monkeypatch)
    monkeypatch.delitem(sys.modules, "scripts.demo_interceptor_guidance", raising=False)

    demo_module = importlib.import_module("scripts.demo_interceptor_guidance")
    demo_module.main()

    output = capsys.readouterr().out
    assert "S3M INTERCEPTOR GUIDANCE DEMO" in output
    assert "PHASE: MIDCOURSE" in output
    assert "PHASE: TERMINAL" in output
    assert "PHASE: ENDGAME" in output
    assert "INTERCEPT RESULT" in output
    assert "Outcome: KILL" in output
    assert "Demo complete. Interceptor guidance computer operational." in output
