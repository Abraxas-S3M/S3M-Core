"""Phase 11 battle planning tests."""

from __future__ import annotations

from src.apps.battle_planning import BattlePlanner, OpsOrderGenerator, PlanToSimBridge


def _sample_brief() -> str:
    return (
        "Conduct a 4-UAV patrol of sector Alpha to detect and report enemy positions. "
        "Avoid engagement unless fired upon."
    )


def test_ops_order_generate_contains_all_paragraphs():
    gen = OpsOrderGenerator()
    opord = gen.generate(_sample_brief())
    assert "paragraphs" in opord
    paragraphs = opord["paragraphs"]
    assert set(paragraphs.keys()) == {"situation", "mission", "execution", "sustainment", "command_signal"}
    assert isinstance(paragraphs["execution"]["tasks"], list)
    assert len(paragraphs["execution"]["tasks"]) >= 1


def test_ops_order_template_fallback_when_llm_unavailable():
    gen = OpsOrderGenerator()
    opord = gen.generate(_sample_brief())
    valid, missing = gen.validate_opord(opord)
    assert valid is True
    assert missing == []


def test_validate_opord_detects_missing_paragraphs():
    gen = OpsOrderGenerator()
    bad = {
        "paragraphs": {
            "situation": {"enemy_forces": "", "friendly_forces": "", "terrain_weather": ""},
            "mission": "",
            "execution": {"concept": "", "tasks": [], "coordinating": ""},
            "sustainment": {"logistics": "", "supply": "", "medical": ""},
            "command_signal": {"command": "", "signal": ""},
        }
    }
    valid, missing = gen.validate_opord(bad)
    assert valid is False
    assert "mission" in missing
    assert "execution.tasks" in missing


def test_plan_to_sim_bridge_returns_scenario_compatible_dict():
    gen = OpsOrderGenerator()
    bridge = PlanToSimBridge()
    opord = gen.generate(_sample_brief())
    scenario = bridge.opord_to_scenario(opord)
    assert "scenario" in scenario
    payload = scenario["scenario"]
    assert "forces" in payload and isinstance(payload["forces"], list)
    assert "objectives" in payload and isinstance(payload["objectives"], list)
    assert "duration_seconds" in payload


def test_battle_planner_quick_assess_returns_string():
    planner = BattlePlanner()
    text = planner.quick_assess("Enemy UAVs detected approaching our FOB from the northeast")
    assert isinstance(text, str)
    assert len(text.strip()) > 0
