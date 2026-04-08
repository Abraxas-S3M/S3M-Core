"""Gymnasium environment bridging Layer 04 wargame scenarios to RL loops."""

from __future__ import annotations

from typing import Any, Dict, List, Sequence

import numpy as np
import yaml

from src.simulation.adapters import BuiltinPhysicsEngine
from src.simulation.models import ScenarioDefinition, SimConfig, SimulationState
from src.simulation.wargame.scenario_engine import ScenarioEngine

try:
    import gymnasium as gym
    from gymnasium import spaces
except Exception:  # pragma: no cover - optional dependency fallback
    gym = None
    spaces = None


ACTION_MOVE = 0
ACTION_ENGAGE = 1
ACTION_HOLD = 2
ACTION_RETREAT = 3


class _SimpleMultiDiscrete:
    def __init__(self, nvec: Sequence[int]) -> None:
        self.nvec = np.asarray(list(nvec), dtype=np.int64)

    def contains(self, value: Any) -> bool:
        arr = np.asarray(value, dtype=np.int64).reshape(-1)
        if arr.shape[0] != self.nvec.shape[0]:
            return False
        return bool(np.all(arr >= 0) and np.all(arr < self.nvec))


class _SimpleBox:
    def __init__(self, shape: tuple[int, ...]) -> None:
        self.shape = shape


class _SimpleDict:
    def __init__(self, mapping: Dict[str, Any]) -> None:
        self.mapping = mapping


class WargameEnv(gym.Env if gym else object):
    """Wrap ScenarioEngine definitions in a Gymnasium-compatible tactical environment."""

    metadata = {"render_modes": []}

    def __init__(
        self,
        scenario_id: str,
        scenarios_dir: str = "configs/scenarios",
        max_units: int = 32,
        max_threats: int = 32,
        tick_dt: float = 1.0,
        max_steps: int | None = None,
    ) -> None:
        sid = str(scenario_id).strip()
        if not sid:
            raise ValueError("scenario_id must be a non-empty string")
        if not isinstance(scenarios_dir, str) or not scenarios_dir.strip():
            raise ValueError("scenarios_dir must be a non-empty string")
        if int(max_units) <= 0:
            raise ValueError("max_units must be > 0")
        if int(max_threats) <= 0:
            raise ValueError("max_threats must be > 0")
        if float(tick_dt) <= 0:
            raise ValueError("tick_dt must be > 0")
        if max_steps is not None and int(max_steps) <= 0:
            raise ValueError("max_steps must be > 0 when provided")

        self.scenario_id = sid
        self.max_units = int(max_units)
        self.max_threats = int(max_threats)
        self.tick_dt = float(tick_dt)
        self.max_steps = int(max_steps) if max_steps is not None else 600

        self._scenario_engine = ScenarioEngine(scenarios_dir=scenarios_dir)
        self._adapter = BuiltinPhysicsEngine(
            SimConfig(
                simulator_name="builtin_rl_env",
                extra_params={"max_entities": min(200, self.max_units + self.max_threats)},
            )
        )
        self._adapter.connect()

        self._scenario: ScenarioDefinition | None = None
        self._friendly_ids: List[str] = []
        self._initial_friendly_count = 0
        self._initial_enemy_count = 0
        self._step_count = 0
        self._objectives_met: set[str] = set()
        self._episode_tuples: List[Dict[str, Any]] = []

        if spaces:
            self.observation_space = spaces.Dict(
                {
                    "unit_positions": spaces.Box(
                        low=-10000.0, high=10000.0, shape=(self.max_units, 3), dtype=np.float32
                    ),
                    "unit_health": spaces.Box(low=0.0, high=1.0, shape=(self.max_units,), dtype=np.float32),
                    "threat_positions": spaces.Box(
                        low=-10000.0, high=10000.0, shape=(self.max_threats, 3), dtype=np.float32
                    ),
                    "threat_levels": spaces.Box(
                        low=0.0, high=1.0, shape=(self.max_threats,), dtype=np.float32
                    ),
                }
            )
            self.action_space = spaces.MultiDiscrete(np.full((self.max_units,), 4, dtype=np.int64))
        else:
            self.observation_space = _SimpleDict(
                {
                    "unit_positions": _SimpleBox((self.max_units, 3)),
                    "unit_health": _SimpleBox((self.max_units,)),
                    "threat_positions": _SimpleBox((self.max_threats, 3)),
                    "threat_levels": _SimpleBox((self.max_threats,)),
                }
            )
            self.action_space = _SimpleMultiDiscrete([4] * self.max_units)

    def _load_scenario(self, scenario_ref: str) -> ScenarioDefinition:
        target = str(scenario_ref).strip()
        candidates = sorted(self._scenario_engine.scenarios_dir.glob("*.yaml"))
        for path in candidates:
            payload = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
            raw = payload.get("scenario", payload)
            if not isinstance(raw, dict):
                continue
            source_id = str(raw.get("scenario_id", "")).strip()
            source_name = str(raw.get("name", "")).strip()
            if target in {source_id, source_name, path.stem}:
                normalized = dict(raw)
                normalized["scenario_id"] = source_id or path.stem
                return self._scenario_engine.load_from_dict(normalized)
        raise ValueError(f"scenario '{target}' not found in {self._scenario_engine.scenarios_dir}")

    def _terrain_center(self) -> tuple[float, float, float]:
        if self._scenario is None:
            return (0.0, 0.0, 0.0)
        bounds = self._scenario.terrain.get("bounds")
        if not isinstance(bounds, list) or len(bounds) != 2:
            return (0.0, 0.0, 0.0)
        try:
            low = tuple(bounds[0])
            high = tuple(bounds[1])
            return (
                (float(low[0]) + float(high[0])) / 2.0,
                (float(low[1]) + float(high[1])) / 2.0,
                (float(low[2]) + float(high[2])) / 2.0,
            )
        except Exception:
            return (0.0, 0.0, 0.0)

    def _retreat_anchor(self) -> tuple[float, float, float]:
        if self._scenario is None:
            return (0.0, 0.0, 0.0)
        bounds = self._scenario.terrain.get("bounds")
        if not isinstance(bounds, list) or len(bounds) != 2:
            return (0.0, 0.0, 0.0)
        try:
            low = tuple(bounds[0])
            return (float(low[0]), float(low[1]), float(low[2]))
        except Exception:
            return (0.0, 0.0, 0.0)

    def _objective_target(self) -> tuple[float, float, float]:
        if self._scenario is None:
            return self._terrain_center()
        params = self._scenario.parameters
        for key in ("patrol_waypoints", "convoy_route"):
            route = params.get(key)
            if isinstance(route, list) and route:
                try:
                    point = tuple(route[-1])
                    return (float(point[0]), float(point[1]), float(point[2]))
                except Exception:
                    continue
        return self._terrain_center()

    def _normalize_action(self, action: Any) -> np.ndarray:
        arr = np.asarray(action, dtype=np.int64).reshape(-1)
        if arr.shape[0] < self.max_units:
            padded = np.full((self.max_units,), ACTION_HOLD, dtype=np.int64)
            padded[: arr.shape[0]] = arr
            arr = padded
        elif arr.shape[0] > self.max_units:
            arr = arr[: self.max_units]
        if hasattr(self.action_space, "contains") and not self.action_space.contains(arr):
            raise ValueError("invalid action vector for tactical unit command set")
        return arr

    def _obs_from_state(self, state: SimulationState) -> Dict[str, np.ndarray]:
        unit_positions = np.zeros((self.max_units, 3), dtype=np.float32)
        unit_health = np.zeros((self.max_units,), dtype=np.float32)
        threat_positions = np.zeros((self.max_threats, 3), dtype=np.float32)
        threat_levels = np.zeros((self.max_threats,), dtype=np.float32)

        friendlies = state.friendly_entities()
        enemies = state.enemy_entities()
        for idx, entity in enumerate(friendlies[: self.max_units]):
            unit_positions[idx] = np.asarray(entity.position, dtype=np.float32)
            unit_health[idx] = np.float32(entity.health)
        for idx, entity in enumerate(enemies[: self.max_threats]):
            threat_positions[idx] = np.asarray(entity.position, dtype=np.float32)
            threat_levels[idx] = np.float32(entity.health)

        return {
            "unit_positions": unit_positions,
            "unit_health": unit_health,
            "threat_positions": threat_positions,
            "threat_levels": threat_levels,
        }

    def _objective_context(self, state: SimulationState) -> Dict[str, Any]:
        friendlies = state.friendly_entities()
        enemies = state.enemy_entities()
        return {
            "all_waypoints_visited": bool(state.metadata.get("all_waypoints_visited", False)),
            "friendly_losses": max(0, self._initial_friendly_count - len(friendlies)),
            "enemy_losses": max(0, self._initial_enemy_count - len(enemies)),
            "enemies_detected": int(state.metadata.get("enemies_detected", len(enemies))),
            "convoy_arrived": bool(state.metadata.get("convoy_arrived", False)),
            "installation_intact": bool(state.metadata.get("installation_intact", True)),
        }

    def _evaluate_objectives(self, state: SimulationState) -> set[str]:
        if self._scenario is None:
            return set()
        context = self._objective_context(state)
        met: set[str] = set()
        for objective in self._scenario.objectives:
            description = str(objective.get("description", "unnamed objective"))
            condition = str(objective.get("success_condition", "False"))
            try:
                if bool(eval(condition, {"__builtins__": {}}, context)):
                    met.add(description)
            except Exception:
                continue
        return met

    def _nearest_enemy_position(self, state: SimulationState, own_position: tuple[float, float, float]) -> tuple[float, float, float]:
        enemies = state.enemy_entities()
        if not enemies:
            return self._objective_target()
        own = np.asarray(own_position, dtype=np.float32)
        nearest = min(
            enemies,
            key=lambda e: float(np.linalg.norm(np.asarray(e.position, dtype=np.float32) - own)),
        )
        return (float(nearest.position[0]), float(nearest.position[1]), float(nearest.position[2]))

    def _apply_unit_actions(self, state: SimulationState, actions: np.ndarray) -> None:
        objective_target = self._objective_target()
        retreat_target = self._retreat_anchor()
        for idx, entity_id in enumerate(self._friendly_ids[: self.max_units]):
            entity = state.get_entity(entity_id)
            if entity is None:
                continue
            action = int(actions[idx])
            if action == ACTION_MOVE:
                target = objective_target
                speed = 10.0
            elif action == ACTION_ENGAGE:
                target = self._nearest_enemy_position(state, entity.position)
                speed = 12.0
            elif action == ACTION_RETREAT:
                target = retreat_target
                speed = 14.0
            else:
                target = entity.position
                speed = 1.0
            # Tactical control: each action maps to an immediate maneuver order.
            self._adapter.set_entity_target(entity_id, target, speed=speed)

    @staticmethod
    def _obs_to_jsonable(obs: Dict[str, np.ndarray]) -> Dict[str, Any]:
        return {k: v.tolist() for k, v in obs.items()}

    def reset(self, seed: int | None = None, options: Dict[str, Any] | None = None):  # type: ignore[override]
        if seed is not None:
            np.random.seed(int(seed))
        scenario_ref = self.scenario_id
        if isinstance(options, dict) and options.get("scenario_id"):
            scenario_ref = str(options["scenario_id"]).strip() or self.scenario_id

        self._scenario = self._load_scenario(scenario_ref)
        duration_steps = int(max(1, self._scenario.duration_seconds / self.tick_dt))
        self.max_steps = min(self.max_steps, duration_steps)

        self._adapter.reset_simulation()
        self._adapter.load_scenario(self._scenario)
        self._adapter.start_simulation()

        state = self._adapter.get_state()
        self._friendly_ids = [entity.entity_id for entity in state.friendly_entities()][: self.max_units]
        self._initial_friendly_count = len(state.friendly_entities())
        self._initial_enemy_count = len(state.enemy_entities())
        self._step_count = 0
        self._objectives_met = set()
        self._episode_tuples = []
        obs = self._obs_from_state(state)
        return obs, {"scenario_id": self._scenario.scenario_id}

    def step(self, action: Any):  # type: ignore[override]
        if self._scenario is None:
            raise RuntimeError("environment must be reset before stepping")

        action_vec = self._normalize_action(action)
        prev_state = self._adapter.get_state()
        prev_obs = self._obs_from_state(prev_state)
        prev_friendly_count = len(prev_state.friendly_entities())

        self._apply_unit_actions(prev_state, action_vec)
        next_state = self._adapter.step(self.tick_dt)
        self._step_count += 1

        newly_met = self._evaluate_objectives(next_state) - self._objectives_met
        self._objectives_met.update(newly_met)
        friendly_loss_delta = max(0, prev_friendly_count - len(next_state.friendly_entities()))

        reward = (-0.5) + (1.0 * len(newly_met)) - (1.0 * friendly_loss_delta)
        terminated = False
        truncated = False

        if len(next_state.friendly_entities()) == 0:
            terminated = True
        if self._scenario.objectives and len(self._objectives_met) >= len(self._scenario.objectives):
            terminated = True
        if next_state.sim_time_seconds >= self._scenario.duration_seconds:
            terminated = True
        if self._step_count >= self.max_steps:
            truncated = True

        obs = self._obs_from_state(next_state)
        self._episode_tuples.append(
            {
                "observation": self._obs_to_jsonable(prev_obs),
                "action": action_vec.tolist(),
                "reward": float(reward),
            }
        )
        info = {
            "step": self._step_count,
            "objectives_met": sorted(self._objectives_met),
            "friendly_losses": max(0, self._initial_friendly_count - len(next_state.friendly_entities())),
        }
        return obs, float(reward), bool(terminated), bool(truncated), info

    def get_episode_tuples(self) -> List[Dict[str, Any]]:
        """Return (observation, action, reward) tuples for downstream RL dataset ingestion."""
        return list(self._episode_tuples)

    def render(self):  # pragma: no cover - no renderer in headless cloud agent
        return None

    def close(self):  # pragma: no cover - trivial resource cleanup
        self._adapter.stop_simulation()
        self._adapter.disconnect()
        return None
