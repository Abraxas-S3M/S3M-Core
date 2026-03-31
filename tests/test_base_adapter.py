#!/usr/bin/env python3
"""Tests for built-in physics adapter behavior."""

from __future__ import annotations

from src.simulation.adapters.base_adapter import BuiltinPhysicsEngine
from src.simulation.models import EntityType, ForceComposition, ScenarioDefinition, SimConfig


def _engine() -> BuiltinPhysicsEngine:
    engine = BuiltinPhysicsEngine(SimConfig(simulator_name="builtin", extra_params={"max_entities": 200}))
    engine.connect()
    return engine


def test_builtin_connect_disconnect():
    engine = _engine()
    assert engine.is_connected() is True
    engine.disconnect()
    assert engine.is_connected() is False


def test_spawn_entity_and_get_state():
    engine = _engine()
    entity_id = engine.spawn_entity(EntityType.FRIENDLY_UAV, (10.0, 10.0, 50.0))
    state = engine.get_state()
    assert state.get_entity(entity_id) is not None


def test_step_advances_toward_target():
    engine = _engine()
    entity_id = engine.spawn_entity(EntityType.FRIENDLY_UAV, (0.0, 0.0, 10.0))
    engine.set_entity_target(entity_id, (100.0, 0.0, 10.0), speed=10.0)
    engine.start_simulation()
    state_1 = engine.step(1.0)
    entity_1 = state_1.get_entity(entity_id)
    assert entity_1 is not None
    assert entity_1.position[0] > 0.0


def test_collision_detection_and_damage():
    engine = _engine()
    friendly_id = engine.spawn_entity(EntityType.FRIENDLY_UAV, (0.0, 0.0, 10.0))
    enemy_id = engine.spawn_entity(EntityType.ENEMY_UAV, (0.0, 0.0, 10.0))
    engine.start_simulation()
    state = engine.step(0.1)
    f = state.get_entity(friendly_id)
    e = state.get_entity(enemy_id)
    assert f is not None and e is not None
    assert f.health < 1.0
    assert e.health < 1.0


def test_load_scenario_spawns_all_units():
    engine = _engine()
    scenario = ScenarioDefinition(
        scenario_id="s1",
        name="Adapter scenario",
        description="Adapter test scenario.",
        scenario_type="patrol",
        terrain={"bounds": [[0, 0, 0], [1000, 1000, 200]], "obstacles": []},
        weather={"visibility": 1.0},
        forces=[
            ForceComposition(
                force_name="Blue",
                allegiance="friendly",
                units=[{"type": EntityType.FRIENDLY_UAV, "count": 2, "starting_position": (10, 10, 10), "behavior": "patrol"}],
            ),
            ForceComposition(
                force_name="Red",
                allegiance="enemy",
                units=[{"type": EntityType.ENEMY_UAV, "count": 3, "starting_position": (20, 20, 10), "behavior": "intercept"}],
            ),
        ],
        objectives=[{"description": "Hold", "success_condition": "friendly_losses == 0", "priority": 1}],
        rules_of_engagement="weapons_tight",
        duration_seconds=120,
        parameters={},
    )
    assert engine.load_scenario(scenario) is True
    assert len(engine.get_state().entities) == 5


def test_max_entity_limit_enforced():
    engine = _engine()
    for idx in range(200):
        engine.spawn_entity(EntityType.FRIENDLY_UGV, (float(idx), 0.0, 0.0))
    try:
        engine.spawn_entity(EntityType.FRIENDLY_UGV, (1000.0, 0.0, 0.0))
        assert False, "Expected max entity limit exception"
    except ValueError:
        assert True
