"""Adaptive and scripted OPFOR behavior generation for scenario execution."""

from __future__ import annotations

from json import loads
from random import Random
from typing import Dict, List

from src.llm_core.engine_registry import TaskDomain
from src.llm_core.orchestrator import Orchestrator, QueryRequest
from src.simulation.adapters.base_adapter import GenericSimAdapter
from src.simulation.models import SimulationState


class OpForGenerator:
    """Generates enemy behavior plans for tactical simulations."""

    def __init__(self, strategy: str = "adaptive") -> None:
        if strategy not in {"static", "scripted", "random", "adaptive"}:
            raise ValueError("strategy must be static/scripted/random/adaptive")
        self.strategy = strategy
        self.difficulty = "medium"
        self._rng = Random(31)
        self._orchestrator = Orchestrator()
        self._decision_interval_ticks = 50
        self._last_decision_tick = -1
        self._cached_behaviors: List[dict] = []

    def _bounds(self, state: SimulationState) -> tuple[tuple[float, float, float], tuple[float, float, float]]:
        bounds = state.terrain.get("bounds")
        if (
            isinstance(bounds, list)
            and len(bounds) == 2
            and isinstance(bounds[0], (list, tuple))
            and isinstance(bounds[1], (list, tuple))
        ):
            return (tuple(float(v) for v in bounds[0]), tuple(float(v) for v in bounds[1]))
        return (0.0, 0.0, 0.0), (1000.0, 1000.0, 200.0)

    def _random_target(self, bounds: tuple[tuple[float, float, float], tuple[float, float, float]]) -> tuple[float, float, float]:
        (min_x, min_y, min_z), (max_x, max_y, max_z) = bounds
        return (
            self._rng.uniform(min_x, max_x),
            self._rng.uniform(min_y, max_y),
            self._rng.uniform(min_z, max_z),
        )

    def _scripted_behavior(self, state: SimulationState) -> List[dict]:
        actions: List[dict] = []
        bounds = self._bounds(state)
        enemies = state.enemy_entities()
        for idx, entity in enumerate(enemies):
            waypoint = (
                bounds[0][0] + ((idx + 1) * 75.0) % (bounds[1][0] - bounds[0][0]),
                bounds[0][1] + ((idx + 1) * 55.0) % (bounds[1][1] - bounds[0][1]),
                max(entity.position[2], 30.0),
            )
            actions.append(
                {
                    "entity_id": entity.entity_id,
                    "action": "move",
                    "target_position": waypoint,
                    "reasoning": "Scripted patrol path for red-force pressure on blue patrol lanes.",
                }
            )
        return actions

    def _random_behavior(self, state: SimulationState) -> List[dict]:
        actions: List[dict] = []
        bounds = self._bounds(state)
        for entity in state.enemy_entities():
            actions.append(
                {
                    "entity_id": entity.entity_id,
                    "action": "move",
                    "target_position": self._random_target(bounds),
                    "reasoning": "Randomized maneuver to create unpredictable OPFOR contact patterns.",
                }
            )
        return actions

    def _adaptive_behavior(self, state: SimulationState) -> List[dict]:
        tick = int(state.metadata.get("tick_count", 0))
        if self._cached_behaviors and (tick - self._last_decision_tick) < self._decision_interval_ticks:
            return self._cached_behaviors

        friendlies = [
            {"entity_id": entity.entity_id, "position": entity.position}
            for entity in state.friendly_entities()
        ]
        enemies = [
            {"entity_id": entity.entity_id, "position": entity.position}
            for entity in state.enemy_entities()
        ]
        prompt = (
            "You are the Red Force commander. "
            f"Current situation: sim_time={state.sim_time_seconds:.2f}s. "
            f"Friendly force (Blue) positions: {friendlies}. "
            f"Your forces: {enemies}. "
            "Generate tactical orders for each of your units. "
            "Respond with a JSON list of "
            "{entity_id, action, target_position, reasoning}."
        )
        try:
            response = self._orchestrator.process(
                QueryRequest(prompt=prompt, domain=TaskDomain.REASONING, require_consensus=False)
            )
            text = getattr(response, "text", "") or ""
            parsed = loads(text)
            if isinstance(parsed, list):
                sanitized = []
                for item in parsed:
                    if not isinstance(item, dict):
                        continue
                    target = item.get("target_position")
                    if not (isinstance(target, list) or isinstance(target, tuple)) or len(target) != 3:
                        continue
                    sanitized.append(
                        {
                            "entity_id": str(item.get("entity_id", "")),
                            "action": str(item.get("action", "move")).lower(),
                            "target_position": (
                                float(target[0]),
                                float(target[1]),
                                float(target[2]),
                            ),
                            "reasoning": str(item.get("reasoning", "Adaptive red-force maneuver.")),
                        }
                    )
                if sanitized:
                    self._cached_behaviors = sanitized
                    self._last_decision_tick = tick
                    return sanitized
        except Exception:
            pass

        fallback = self._random_behavior(state)
        self._cached_behaviors = fallback
        self._last_decision_tick = tick
        return fallback

    def generate_behavior(self, state: SimulationState, force_name: str = "Red Force") -> List[dict]:
        """Generate OPFOR actions using selected strategy."""
        _ = force_name
        if self.strategy == "static":
            return []
        if self.strategy == "scripted":
            return self._scripted_behavior(state)
        if self.strategy == "random":
            return self._random_behavior(state)
        return self._adaptive_behavior(state)

    def apply_behavior(self, adapter: GenericSimAdapter, behaviors: List[dict]) -> None:
        """Apply generated actions to adapter movement/engagement controls."""
        for behavior in behaviors:
            if not isinstance(behavior, dict):
                continue
            entity_id = str(behavior.get("entity_id", ""))
            action = str(behavior.get("action", "move")).lower()
            target = behavior.get("target_position", (0.0, 0.0, 0.0))
            if not entity_id or not isinstance(target, (list, tuple)) or len(target) != 3:
                continue
            if action in {"move", "engage", "retreat"}:
                speed = 8.0 if self.difficulty == "easy" else 12.0
                if self.difficulty in {"hard", "nightmare"}:
                    speed = 16.0
                adapter.set_entity_target(
                    entity_id=entity_id,
                    target_position=(float(target[0]), float(target[1]), float(target[2])),
                    speed=speed,
                )

    def set_difficulty(self, level: str) -> None:
        """Set OPFOR difficulty profile impacting response speed and aggression."""
        if level not in {"easy", "medium", "hard", "nightmare"}:
            raise ValueError("difficulty must be easy/medium/hard/nightmare")
        self.difficulty = level
        self._decision_interval_ticks = {
            "easy": 80,
            "medium": 50,
            "hard": 30,
            "nightmare": 15,
        }[level]
