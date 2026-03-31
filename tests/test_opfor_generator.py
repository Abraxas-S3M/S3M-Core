"""Tests for OPFOR behavior generation and adapter application."""

from __future__ import annotations

from datetime import datetime, timezone

from src.simulation.adapters.base_adapter import BuiltinPhysicsEngine
from src.simulation.models import EntityType, SimConfig, SimulationState
from src.simulation.wargame.opfor_generator import OpForGenerator


def _state() -> SimulationState:
    engine = BuiltinPhysicsEngine(SimConfig(simulator_name="builtin"))
    engine.connect()
    engine.spawn_entity(EntityType.FRIENDLY_UAV, (50.0, 50.0, 60.0))
    engine.spawn_entity(EntityType.ENEMY_UAV, (500.0, 500.0, 70.0))
    return engine.get_state()


def test_static_strategy_returns_empty_actions():
    generator = OpForGenerator(strategy="static")
    actions = generator.generate_behavior(_state())
    assert actions == []


def test_random_strategy_returns_valid_targets_in_bounds():
    state = _state()
    state.terrain = {"bounds": [[0, 0, 0], [1000, 1000, 200]]}
    generator = OpForGenerator(strategy="random")
    actions = generator.generate_behavior(state)
    assert len(actions) == 1
    tx, ty, tz = actions[0]["target_position"]
    assert 0 <= tx <= 1000
    assert 0 <= ty <= 1000
    assert 0 <= tz <= 200


def test_adaptive_strategy_falls_back_when_llm_unparseable():
    generator = OpForGenerator(strategy="adaptive")
    state = _state()
    actions = generator.generate_behavior(state)
    assert isinstance(actions, list)
    assert len(actions) == 1
    assert actions[0]["action"] in {"move", "engage", "retreat", "hold"}


def test_apply_behavior_calls_set_entity_target():
    class DummyAdapter:
        def __init__(self):
            self.calls = []

        def set_entity_target(self, entity_id, target_position, speed=10.0):
            self.calls.append((entity_id, target_position, speed))

    adapter = DummyAdapter()
    generator = OpForGenerator(strategy="random")
    generator.apply_behavior(
        adapter,
        [{"entity_id": "e1", "action": "move", "target_position": (1.0, 2.0, 3.0), "reasoning": "test"}],
    )
    assert len(adapter.calls) == 1
    assert adapter.calls[0][0] == "e1"

