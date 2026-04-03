"""Unit tests for edge runtime degradation controller state machine."""

from __future__ import annotations

import os
import sys
from typing import List, Tuple

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.edge_runtime.degradation_controller import DegradationController, OperatingMode
from src.edge_runtime.hardware_profiler import HardwareTier, NodeProfile


def _profile(
    *,
    tier: HardwareTier = HardwareTier.FULL_EDGE,
    gpu_detected: bool = True,
    active_links: List[str] | None = None,
    thermal_zone_c: float | None = 40.0,
    ram_available_gb: float = 8.0,
) -> NodeProfile:
    return NodeProfile(
        tier=tier,
        gpu_detected=gpu_detected,
        active_links=["lte"] if active_links is None else active_links,
        thermal_zone_c=thermal_zone_c,
        ram_available_gb=ram_available_gb,
    )


def test_initial_mode_cpu_austere_starts_mode_b() -> None:
    controller = DegradationController(_profile(tier=HardwareTier.CPU_AUSTERE))
    assert controller.current_mode == OperatingMode.MODE_B_CPU_CONSTRAINED
    assert controller.current_policy().allow_gpu is False


def test_initial_mode_no_links_starts_mode_d() -> None:
    controller = DegradationController(_profile(active_links=[]))
    assert controller.current_mode == OperatingMode.MODE_D_OFFLINE_SURVIVAL
    assert controller.current_policy().queue_outbound is True


def test_initial_mode_full_edge_when_links_and_resources_available() -> None:
    controller = DegradationController(_profile())
    assert controller.current_mode == OperatingMode.MODE_A_FULL_EDGE
    assert controller.current_policy().allow_continuous_summarization is True


def test_reevaluate_enters_mode_b_when_thermal_hot() -> None:
    controller = DegradationController(_profile())
    controller.report_thermal(90.0)
    assert controller.current_mode == OperatingMode.MODE_B_CPU_CONSTRAINED
    assert controller.get_transition_log()[-1]["reason"] == "hw_constrained"


def test_reevaluate_enters_mode_b_when_ram_low() -> None:
    controller = DegradationController(_profile(ram_available_gb=3.5))
    controller.report_link_state(True)
    assert controller.current_mode == OperatingMode.MODE_B_CPU_CONSTRAINED


def test_reevaluate_enters_mode_c_after_intermittent_link(monkeypatch: pytest.MonkeyPatch) -> None:
    now = 1_000.0
    monkeypatch.setattr("src.edge_runtime.degradation_controller.time.time", lambda: now)
    controller = DegradationController(_profile())
    controller.report_link_state(False)
    now += 61.0
    controller.report_link_state(False)
    assert controller.current_mode == OperatingMode.MODE_C_INTERMITTENT_LINK
    assert controller.get_transition_log()[-1]["reason"] == "link_intermittent"


def test_reevaluate_enters_mode_d_after_5min_no_link_cpu_only(monkeypatch: pytest.MonkeyPatch) -> None:
    now = 2_000.0
    monkeypatch.setattr("src.edge_runtime.degradation_controller.time.time", lambda: now)
    controller = DegradationController(_profile(gpu_detected=False))
    controller.report_link_state(False)
    now += 301.0
    controller.report_link_state(False)
    assert controller.current_mode == OperatingMode.MODE_D_OFFLINE_SURVIVAL
    assert controller.get_transition_log()[-1]["reason"] == "no_link_5min_cpu_only"


def test_reevaluate_enters_mode_d_after_10min_no_link_even_with_gpu(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    now = 3_000.0
    monkeypatch.setattr("src.edge_runtime.degradation_controller.time.time", lambda: now)
    controller = DegradationController(_profile(gpu_detected=True))
    controller.report_link_state(False)
    now += 601.0
    controller.report_link_state(False)
    assert controller.current_mode == OperatingMode.MODE_D_OFFLINE_SURVIVAL
    assert controller.get_transition_log()[-1]["reason"] == "no_link_10min"


def test_recovery_path_returns_to_mode_a_when_link_restored() -> None:
    controller = DegradationController(_profile())
    controller.report_thermal(95.0)
    assert controller.current_mode == OperatingMode.MODE_B_CPU_CONSTRAINED
    controller.report_thermal(55.0)
    assert controller.current_mode == OperatingMode.MODE_A_FULL_EDGE
    assert controller.get_transition_log()[-1]["to"] == OperatingMode.MODE_A_FULL_EDGE.value


def test_force_mode_records_transition_and_notifies_subscriber() -> None:
    controller = DegradationController(_profile())
    seen: List[Tuple[OperatingMode, bool]] = []

    def _subscriber(mode: OperatingMode, policy) -> None:
        seen.append((mode, policy.allow_gpu))

    controller.subscribe(_subscriber)
    controller.force_mode(OperatingMode.MODE_C_INTERMITTENT_LINK, reason="manual_drill")
    assert controller.current_mode == OperatingMode.MODE_C_INTERMITTENT_LINK
    assert controller.get_transition_log()[-1]["reason"] == "manual_drill"
    assert seen == [(OperatingMode.MODE_C_INTERMITTENT_LINK, True)]


def test_service_tiers_includes_required_tier0_services() -> None:
    tiers = DegradationController.service_tiers()
    for service_name in (
        "llm_inference_q4",
        "threat_classifier",
        "anomaly_detector",
        "behavior_tree_exec",
        "sensor_fusion_ekf",
    ):
        assert tiers[service_name]["tier"] == 0
        assert tiers[service_name]["cpu_safe"] is True
