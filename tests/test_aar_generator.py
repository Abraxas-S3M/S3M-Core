"""Tests for AAR generation and comparison utilities."""

from __future__ import annotations

from datetime import datetime, timezone

from src.simulation.models import (
    EntityType,
    ForceComposition,
    ScenarioDefinition,
    SimEntity,
    SimulationState,
)
from src.simulation.wargame.aar_generator import AARGenerator


def _scenario() -> ScenarioDefinition:
    return ScenarioDefinition(
        scenario_id="scn-1",
        name="AAR Scenario",
        description="Test scenario",
        scenario_type="patrol",
        terrain={"bounds": [[0, 0, 0], [100, 100, 100]]},
        weather={},
        forces=[
            ForceComposition(
                force_name="Blue",
                allegiance="friendly",
                units=[{"type": EntityType.FRIENDLY_UAV, "count": 2, "starting_position": (10, 10, 20), "behavior": "patrol"}],
            ),
            ForceComposition(
                force_name="Red",
                allegiance="enemy",
                units=[{"type": EntityType.ENEMY_UAV, "count": 2, "starting_position": (60, 60, 20), "behavior": "intercept"}],
            ),
        ],
        objectives=[
            {"description": "Enemy losses >= 1", "success_condition": "enemy_losses >= 1", "priority": 1},
        ],
        rules_of_engagement="weapons_free",
        duration_seconds=120,
        parameters={},
    )


def test_generate_produces_aar_report():
    generator = AARGenerator()
    scenario = _scenario()
    state = SimulationState(
        timestamp=datetime.now(timezone.utc),
        sim_time_seconds=30.0,
        entities=[
            SimEntity("f1", EntityType.FRIENDLY_UAV, (1, 1, 1), (0, 0, 0), 0, 1.0, True, {}),
            SimEntity("e1", EntityType.ENEMY_UAV, (2, 2, 2), (0, 0, 0), 0, 1.0, True, {}),
        ],
        terrain={},
        weather={},
        active_events=[],
        metadata={},
    )
    aar = generator.generate(scenario, state, timeline=[])
    assert aar.scenario_id == scenario.scenario_id
    assert aar.duration_seconds == 30.0


def test_victory_condition_all_primary_objectives_met():
    generator = AARGenerator()
    scenario = _scenario()
    state = SimulationState(
        timestamp=datetime.now(timezone.utc),
        sim_time_seconds=45.0,
        entities=[SimEntity("f1", EntityType.FRIENDLY_UAV, (1, 1, 1), (0, 0, 0), 0, 1.0, True, {})],
        terrain={},
        weather={},
        active_events=[],
        metadata={},
    )
    aar = generator.generate(scenario, state, timeline=[])
    assert aar.outcome == "victory"


def test_defeat_condition_all_friendlies_lost():
    generator = AARGenerator()
    scenario = _scenario()
    state = SimulationState(
        timestamp=datetime.now(timezone.utc),
        sim_time_seconds=60.0,
        entities=[SimEntity("e1", EntityType.ENEMY_UAV, (2, 2, 2), (0, 0, 0), 0, 1.0, True, {})],
        terrain={},
        weather={},
        active_events=[],
        metadata={},
    )
    aar = generator.generate(scenario, state, timeline=[])
    assert aar.outcome == "defeat"


def test_generate_comparison_two_aars():
    generator = AARGenerator()
    scenario = _scenario()
    state1 = SimulationState(
        timestamp=datetime.now(timezone.utc),
        sim_time_seconds=30.0,
        entities=[SimEntity("f1", EntityType.FRIENDLY_UAV, (1, 1, 1), (0, 0, 0), 0, 1.0, True, {})],
        terrain={},
        weather={},
        active_events=[],
        metadata={},
    )
    state2 = SimulationState(
        timestamp=datetime.now(timezone.utc),
        sim_time_seconds=30.0,
        entities=[SimEntity("e1", EntityType.ENEMY_UAV, (2, 2, 2), (0, 0, 0), 0, 1.0, True, {})],
        terrain={},
        weather={},
        active_events=[],
        metadata={},
    )
    aar1 = generator.generate(scenario, state1, timeline=[])
    aar2 = generator.generate(scenario, state2, timeline=[])
    summary = generator.generate_comparison([aar1, aar2])
    assert summary["total_runs"] == 2
    assert "best_run" in summary


def test_fallback_when_llm_unavailable_statistics_only():
    generator = AARGenerator()
    generator._orchestrator = object()  # force query failure path
    scenario = _scenario()
    state = SimulationState(
        timestamp=datetime.now(timezone.utc),
        sim_time_seconds=10.0,
        entities=[],
        terrain={},
        weather={},
        active_events=[],
        metadata={},
    )
    aar = generator.generate(scenario, state, timeline=[])
    assert isinstance(aar.statistics, dict)
