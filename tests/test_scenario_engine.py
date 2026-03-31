"""Unit tests for scenario loading, validation, and listing workflows."""

from __future__ import annotations

import json
from pathlib import Path

from src.simulation.models import EntityType, ForceComposition
from src.simulation.wargame.scenario_engine import ScenarioEngine


def _valid_payload() -> dict:
    return {
        "scenario": {
            "name": "Urban Patrol Test",
            "type": "patrol",
            "description": "Patrol scenario for validation.",
            "terrain": {"bounds": [[0, 0, 0], [1000, 1000, 200]], "type": "urban", "obstacles": []},
            "weather": {"visibility": 0.9, "wind_speed": 5.0, "wind_direction": 270, "precipitation": "none"},
            "forces": [
                {
                    "name": "Blue Force",
                    "allegiance": "friendly",
                    "units": [{"type": "FRIENDLY_UAV", "count": 4, "position": [100, 100, 80], "behavior": "patrol"}],
                }
            ],
            "objectives": [{"description": "Complete patrol", "success_condition": "all_waypoints_visited", "priority": 1}],
            "rules_of_engagement": "weapons_tight",
            "duration_seconds": 600,
            "parameters": {},
        }
    }


def test_load_from_dict_valid():
    engine = ScenarioEngine()
    scenario = engine.load_from_dict(_valid_payload())
    assert scenario.name == "Urban Patrol Test"
    assert scenario.scenario_type == "patrol"


def test_validation_missing_forces():
    engine = ScenarioEngine()
    payload = _valid_payload()
    payload["scenario"]["forces"] = []
    try:
        engine.load_from_dict(payload)
    except ValueError as exc:
        assert "force" in str(exc).lower()
    else:
        assert False, "Expected validation error"


def test_validation_invalid_positions():
    engine = ScenarioEngine()
    payload = _valid_payload()
    payload["scenario"]["forces"][0]["units"][0]["position"] = [2000, 2000, 80]
    try:
        engine.load_from_dict(payload)
    except ValueError as exc:
        assert "bounds" in str(exc).lower()
    else:
        assert False, "Expected bounds validation error"


def test_create_scenario_programmatic():
    engine = ScenarioEngine()
    force = ForceComposition(
        force_name="Blue Programmatic",
        allegiance="friendly",
        units=[{"type": EntityType.FRIENDLY_UAV, "count": 2, "starting_position": (10, 10, 20), "behavior": "patrol"}],
    )
    scenario = engine.create_scenario(
        name="Programmatic",
        scenario_type="patrol",
        forces=[force],
        objectives=[{"description": "Stay alive", "success_condition": "friendly_losses == 0", "priority": 1}],
    )
    assert scenario.total_units() == 2


def test_list_scenarios_finds_yaml(tmp_path: Path):
    scenarios_dir = tmp_path / "scenarios"
    scenarios_dir.mkdir(parents=True, exist_ok=True)
    payload = _valid_payload()
    path = scenarios_dir / "test.yaml"
    import yaml

    path.write_text(yaml.safe_dump(payload), encoding="utf-8")
    engine = ScenarioEngine(str(scenarios_dir))
    listed = engine.list_scenarios()
    assert any(item["path"].endswith("test.yaml") for item in listed)
