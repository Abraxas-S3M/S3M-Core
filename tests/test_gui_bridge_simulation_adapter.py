"""Tests for simulation workspace adapter behavior."""

from __future__ import annotations

import sys
import types

from src.api.gui_bridge.adapters.simulation_adapter import SimulationAdapter


class _ManagerWithCatalog:
    def get_scenario_catalog(self):
        return [
            {
                "scenario_id": "WG-001",
                "name": "Northern Shield",
                "description": "Combined-arms rehearsal",
                "status": "ready",
                "scenario_type": "wargame",
                "updated_at": "2026-01-01T00:00:00+00:00",
            }
        ]


class _BrokenManager:
    def __init__(self):
        raise RuntimeError("manager unavailable")


class _RecorderWithGet:
    def get(self, scenario_id: str):
        return {"outcome": "victory", "scenarioId": scenario_id}


class _RecorderWithoutGet:
    pass


class _SuiteWithStats:
    def get_statistics(self):
        return {"total_sessions": 3}


def test_get_scenario_catalog_maps_training_manager_payload(monkeypatch) -> None:
    monkeypatch.setitem(
        sys.modules,
        "apps.simulation.manager",
        types.SimpleNamespace(TrainingSimManager=_ManagerWithCatalog),
    )

    payload = SimulationAdapter().get_scenario_catalog()
    assert "scenarios" in payload
    assert payload["scenarios"][0]["id"] == "WG-001"
    assert payload["scenarios"][0]["type"] == "wargame"


def test_get_scenario_catalog_falls_back_when_manager_errors(monkeypatch) -> None:
    monkeypatch.setitem(
        sys.modules,
        "apps.simulation.manager",
        types.SimpleNamespace(TrainingSimManager=_BrokenManager),
    )
    payload = SimulationAdapter().get_scenario_catalog()
    assert "scenarios" in payload
    assert isinstance(payload["scenarios"], list)


def test_get_aar_uses_recorder_get_when_available(monkeypatch) -> None:
    monkeypatch.setitem(
        sys.modules,
        "src.validation.aar_recorder",
        types.SimpleNamespace(AARRecorder=_RecorderWithGet),
    )
    payload = SimulationAdapter().get_aar("SCN-9")
    assert payload["scenarioId"] == "SCN-9"
    assert payload["aar"]["outcome"] == "victory"


def test_get_aar_returns_empty_when_recorder_has_no_get(monkeypatch) -> None:
    monkeypatch.setitem(
        sys.modules,
        "src.validation.aar_recorder",
        types.SimpleNamespace(AARRecorder=_RecorderWithoutGet),
    )
    payload = SimulationAdapter().get_aar("SCN-10")
    assert payload["scenarioId"] == "SCN-10"
    assert payload["aar"] == {}


def test_run_comparison_returns_comparison_payload(monkeypatch) -> None:
    monkeypatch.setitem(
        sys.modules,
        "apps.simulation.wargaming",
        types.SimpleNamespace(WargameSuite=_SuiteWithStats),
    )
    payload = SimulationAdapter().run_comparison("SCN-11")
    assert "comparison" in payload
    assert payload["comparison"]["scenarioId"] == "SCN-11"
    assert payload["comparison"]["suiteStats"]["total_sessions"] == 3
