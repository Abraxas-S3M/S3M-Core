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


class _FakeWargameEnv:
    def __init__(self, scenario_id: str):
        self.scenario_id = scenario_id
        self.max_units = 4
        self._episode_tuples = []

    def reset(self, options=None):
        self._episode_tuples = []
        obs = {
            "unit_health": [1.0, 0.0, 0.0, 0.0],
            "threat_levels": [1.0, 0.0, 0.0, 0.0],
        }
        return obs, {"scenario_id": self.scenario_id}

    def step(self, actions):
        reward = 1.0 if int(actions[0]) == 1 else 0.5
        obs = {
            "unit_health": [1.0, 0.0, 0.0, 0.0],
            "threat_levels": [0.0, 0.0, 0.0, 0.0],
        }
        self._episode_tuples.append(
            {
                "observation": {"unit_health": [1.0, 0.0, 0.0, 0.0]},
                "action": list(actions),
                "reward": reward,
            }
        )
        info = {"step": 1, "objectives_met": ["obj"], "friendly_losses": 0}
        return obs, reward, True, False, info

    def get_episode_tuples(self):
        return list(self._episode_tuples)

    def close(self):
        return None


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


def test_run_ai_vs_human_returns_metrics_and_training_tuples(monkeypatch) -> None:
    monkeypatch.setitem(
        sys.modules,
        "src.simulation.gym_wargame_env",
        types.SimpleNamespace(
            WargameEnv=_FakeWargameEnv,
            ACTION_MOVE=0,
            ACTION_ENGAGE=1,
            ACTION_HOLD=2,
        ),
    )

    payload = SimulationAdapter().run_ai_vs_human("SCN-12")
    assert payload["comparison"]["scenarioId"] == "SCN-12"
    assert payload["comparison"]["modes"]["ai"] == "rl_agent"
    assert payload["comparison"]["ai"]["totalReward"] == 1.0
    assert payload["comparison"]["human"]["totalReward"] == 0.5
    assert payload["trainingData"]["targetModule"] == "src/training/gpu/dataset_builder.py"
    assert len(payload["trainingData"]["episodes"]) == 2
