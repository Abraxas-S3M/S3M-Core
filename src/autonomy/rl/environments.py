"""Gymnasium-compatible autonomy environments for tactical RL training.

The environments simulate contested operating areas where autonomous agents must
reach objectives while avoiding threats, preserving survivability, and keeping
formation discipline for swarm operations.
"""

from __future__ import annotations

from dataclasses import dataclass
import math
import random
from typing import Any, Dict, List, Tuple

import numpy as np

try:
    import gymnasium as gym
    from gymnasium import spaces
except Exception:  # pragma: no cover - optional dependency
    gym = None
    spaces = None

try:
    from pettingzoo import ParallelEnv as PettingZooParallelEnv
except Exception:  # pragma: no cover - optional dependency
    PettingZooParallelEnv = object  # type: ignore[assignment]


MOVE_FORWARD = 0
TURN_LEFT = 1
TURN_RIGHT = 2
ACCELERATE = 3
DECELERATE = 4
ENGAGE = 5
HOLD = 6


@dataclass
class _SimpleDiscrete:
    n: int

    def sample(self) -> int:
        return random.randint(0, self.n - 1)

    def contains(self, value: Any) -> bool:
        return isinstance(value, int) and 0 <= value < self.n


class _SimpleBox:
    def __init__(self, low: float, high: float, shape: Tuple[int, ...]):
        self.low = low
        self.high = high
        self.shape = shape

    def sample(self) -> np.ndarray:
        return np.random.uniform(self.low, self.high, size=self.shape).astype(np.float32)


class _SimpleDict:
    def __init__(self, mapping: Dict[str, Any]):
        self.mapping = mapping


class MilitaryEnvironment(gym.Env if gym else object):
    """Single-agent tactical navigation environment.

    This models a single autonomous platform moving through contested terrain.
    The objective is to reach a mission waypoint quickly while minimizing
    exposure to nearby threats that can destroy the platform.
    """

    metadata = {"render_modes": []}
    ACTION_MOVE_FORWARD = MOVE_FORWARD
    ACTION_TURN_LEFT = TURN_LEFT
    ACTION_TURN_RIGHT = TURN_RIGHT
    ACTION_ACCELERATE = ACCELERATE
    ACTION_DECELERATE = DECELERATE
    ACTION_ENGAGE = ENGAGE
    ACTION_HOLD = HOLD

    def __init__(self, grid_size: int = 100, max_steps: int = 1000, n_threats: int = 5):
        self.grid_size = int(grid_size)
        self.max_steps = int(max_steps)
        self.n_threats = int(n_threats)
        self.step_count = 0
        self.destroyed = False
        self.weapon_mode = "weapons_hold"
        self.engagement_range = 15.0
        self.default_speed = 1.5

        self.agent_position = np.zeros(3, dtype=np.float32)
        self.agent_heading = 0.0
        self.agent_speed = self.default_speed
        self.threat_positions = np.zeros((self.n_threats, 3), dtype=np.float32)
        self.threat_levels = np.zeros(self.n_threats, dtype=np.float32)
        self.mission_waypoint = np.zeros(3, dtype=np.float32)

        if spaces:
            self.observation_space = spaces.Dict(
                {
                    "agent_position": spaces.Box(0, float(self.grid_size), shape=(3,), dtype=np.float32),
                    "agent_heading": spaces.Box(0, 360, shape=(1,), dtype=np.float32),
                    "agent_speed": spaces.Box(0, 50, shape=(1,), dtype=np.float32),
                    "threat_positions": spaces.Box(
                        0, float(self.grid_size), shape=(self.n_threats, 3), dtype=np.float32
                    ),
                    "threat_levels": spaces.Box(0, 1, shape=(self.n_threats,), dtype=np.float32),
                    "mission_waypoint": spaces.Box(0, float(self.grid_size), shape=(3,), dtype=np.float32),
                }
            )
            self.action_space = spaces.Discrete(7)
        else:
            self.observation_space = _SimpleDict(
                {
                    "agent_position": _SimpleBox(0, float(self.grid_size), (3,)),
                    "agent_heading": _SimpleBox(0, 360, (1,)),
                    "agent_speed": _SimpleBox(0, 50, (1,)),
                    "threat_positions": _SimpleBox(0, float(self.grid_size), (self.n_threats, 3)),
                    "threat_levels": _SimpleBox(0, 1, (self.n_threats,)),
                    "mission_waypoint": _SimpleBox(0, float(self.grid_size), (3,)),
                }
            )
            self.action_space = _SimpleDiscrete(7)

    def _random_position(self) -> np.ndarray:
        return np.random.uniform(0, self.grid_size, size=(3,)).astype(np.float32)

    def _get_obs(self) -> Dict[str, np.ndarray]:
        return {
            "agent_position": self.agent_position.copy(),
            "agent_heading": np.array([self.agent_heading], dtype=np.float32),
            "agent_speed": np.array([self.agent_speed], dtype=np.float32),
            "threat_positions": self.threat_positions.copy(),
            "threat_levels": self.threat_levels.copy(),
            "mission_waypoint": self.mission_waypoint.copy(),
        }

    def reset(self, seed: int | None = None, options: Dict[str, Any] | None = None):  # type: ignore[override]
        if seed is not None:
            random.seed(seed)
            np.random.seed(seed)
        self.step_count = 0
        self.destroyed = False
        self.agent_position = self._random_position()
        self.agent_heading = random.uniform(0, 359.0)
        self.agent_speed = self.default_speed
        self.threat_positions = np.array([self._random_position() for _ in range(self.n_threats)], dtype=np.float32)
        self.threat_levels = np.random.uniform(0.2, 1.0, size=(self.n_threats,)).astype(np.float32)
        self.mission_waypoint = self._random_position()
        obs = self._get_obs()
        return obs, {}

    def _nearest_threat_distance(self) -> float:
        if self.threat_positions.size == 0:
            return float("inf")
        distances = np.linalg.norm(self.threat_positions - self.agent_position, axis=1)
        return float(np.min(distances))

    def _update_kinematics(self, action: int) -> None:
        if action == TURN_LEFT:
            self.agent_heading = (self.agent_heading - 20.0) % 360.0
        elif action == TURN_RIGHT:
            self.agent_heading = (self.agent_heading + 20.0) % 360.0
        elif action == ACCELERATE:
            self.agent_speed = min(12.0, self.agent_speed + 0.5)
        elif action == DECELERATE:
            self.agent_speed = max(0.0, self.agent_speed - 0.5)
        elif action == HOLD:
            self.agent_speed = 0.0

        if action in {MOVE_FORWARD, ENGAGE, HOLD, ACCELERATE, DECELERATE, TURN_LEFT, TURN_RIGHT}:
            rad = math.radians(self.agent_heading)
            delta = np.array([math.cos(rad), math.sin(rad), 0.0], dtype=np.float32) * float(self.agent_speed)
            self.agent_position = self.agent_position + delta

    def step(self, action: int):  # type: ignore[override]
        if hasattr(self.action_space, "contains") and not self.action_space.contains(int(action)):
            raise ValueError("invalid action")

        self.step_count += 1
        reward = -1.0
        info: Dict[str, Any] = {}
        terminated = False
        truncated = False

        self._update_kinematics(int(action))

        out_of_bounds = np.any(self.agent_position < 0) or np.any(self.agent_position > self.grid_size)
        if out_of_bounds:
            reward -= 20.0
            self.agent_position = np.clip(self.agent_position, 0.0, float(self.grid_size))
            info["out_of_bounds"] = True

        nearest = self._nearest_threat_distance()
        threat_distances = np.linalg.norm(self.threat_positions - self.agent_position, axis=1)
        if nearest < 8.0:
            self.destroyed = True
            terminated = True
            reward -= 50.0
            info["destroyed"] = True
        else:
            # Tactical rationale: reward keeping each threat outside immediate danger radius.
            reward += float(np.sum(threat_distances >= 20.0)) * 10.0 / max(1, self.n_threats)

        waypoint_distance = float(np.linalg.norm(self.mission_waypoint - self.agent_position))
        if waypoint_distance <= 5.0:
            reward += 100.0
            terminated = True
            info["objective_reached"] = True

        if self.step_count >= self.max_steps:
            truncated = True

        obs = self._get_obs()
        return obs, float(reward), bool(terminated), bool(truncated), info

    def render(self):  # pragma: no cover - textual no-op
        return None

    def close(self):  # pragma: no cover - no resources to release
        return None

    def get_state_for_llm(self) -> str:
        """Generate tactical state summary for doctrinal LLM consultation."""
        nearest = self._nearest_threat_distance()
        waypoint_distance = float(np.linalg.norm(self.mission_waypoint - self.agent_position))
        return (
            "Agent tactical status: "
            f"position={self.agent_position.tolist()}, "
            f"heading={self.agent_heading:.1f} deg, speed={self.agent_speed:.1f} m/s. "
            f"Nearest threat distance={nearest:.1f} m. "
            f"Waypoint={self.mission_waypoint.tolist()}, distance={waypoint_distance:.1f} m. "
            f"Step={self.step_count}/{self.max_steps}."
        )


class DroneSwarmEnv(PettingZooParallelEnv):
    """Multi-agent extension of contested-terrain environment for swarm training."""

    metadata = {"name": "s3m_drone_swarm_env"}

    def __init__(self, n_agents: int = 4, grid_size: int = 200, max_steps: int = 2000, n_threats: int = 10):
        self.n_agents = int(n_agents)
        self.grid_size = int(grid_size)
        self.max_steps = int(max_steps)
        self.n_threats = int(n_threats)
        self.agents = [f"agent_{idx}" for idx in range(self.n_agents)]
        self.possible_agents = list(self.agents)
        self.step_count = 0
        self.target_spacing = 20.0

        self.agent_positions: Dict[str, np.ndarray] = {
            aid: np.zeros(3, dtype=np.float32) for aid in self.agents
        }
        self.agent_headings: Dict[str, float] = {aid: 0.0 for aid in self.agents}
        self.agent_speeds: Dict[str, float] = {aid: 1.5 for aid in self.agents}
        self.agent_destroyed: Dict[str, bool] = {aid: False for aid in self.agents}

        self.threat_positions = np.zeros((self.n_threats, 3), dtype=np.float32)
        self.threat_levels = np.zeros(self.n_threats, dtype=np.float32)
        self.mission_waypoint = np.zeros(3, dtype=np.float32)

        if spaces:
            self.single_observation_space = spaces.Dict(
                {
                    "agent_position": spaces.Box(0, float(self.grid_size), shape=(3,), dtype=np.float32),
                    "agent_heading": spaces.Box(0, 360, shape=(1,), dtype=np.float32),
                    "agent_speed": spaces.Box(0, 50, shape=(1,), dtype=np.float32),
                    "threat_positions": spaces.Box(
                        0, float(self.grid_size), shape=(self.n_threats, 3), dtype=np.float32
                    ),
                    "threat_levels": spaces.Box(0, 1, shape=(self.n_threats,), dtype=np.float32),
                    "mission_waypoint": spaces.Box(0, float(self.grid_size), shape=(3,), dtype=np.float32),
                }
            )
            self.single_action_space = spaces.Discrete(7)
        else:
            self.single_observation_space = _SimpleDict({})
            self.single_action_space = _SimpleDiscrete(7)

    def observation_space(self, agent: str):  # type: ignore[override]
        return self.single_observation_space

    def action_space(self, agent: str):  # type: ignore[override]
        return self.single_action_space

    def _random_position(self) -> np.ndarray:
        return np.random.uniform(0, self.grid_size, size=(3,)).astype(np.float32)

    def _obs_for(self, agent_id: str) -> Dict[str, np.ndarray]:
        return {
            "agent_position": self.agent_positions[agent_id].copy(),
            "agent_heading": np.array([self.agent_headings[agent_id]], dtype=np.float32),
            "agent_speed": np.array([self.agent_speeds[agent_id]], dtype=np.float32),
            "threat_positions": self.threat_positions.copy(),
            "threat_levels": self.threat_levels.copy(),
            "mission_waypoint": self.mission_waypoint.copy(),
        }

    def reset(self, seed: int | None = None, options: Dict[str, Any] | None = None):
        if seed is not None:
            random.seed(seed)
            np.random.seed(seed)
        self.step_count = 0
        self.agents = list(self.possible_agents)
        self.threat_positions = np.array([self._random_position() for _ in range(self.n_threats)], dtype=np.float32)
        self.threat_levels = np.random.uniform(0.2, 1.0, size=(self.n_threats,)).astype(np.float32)
        self.mission_waypoint = self._random_position()
        self.agent_positions = {aid: self._random_position() for aid in self.agents}
        self.agent_headings = {aid: random.uniform(0, 359.0) for aid in self.agents}
        self.agent_speeds = {aid: 1.5 for aid in self.agents}
        self.agent_destroyed = {aid: False for aid in self.agents}
        observations = {aid: self._obs_for(aid) for aid in self.agents}
        infos = {aid: {} for aid in self.agents}
        return observations, infos

    def _nearest_threat(self, pos: np.ndarray) -> float:
        return float(np.min(np.linalg.norm(self.threat_positions - pos, axis=1)))

    def _apply_action(self, agent_id: str, action: int) -> None:
        if action == TURN_LEFT:
            self.agent_headings[agent_id] = (self.agent_headings[agent_id] - 20.0) % 360.0
        elif action == TURN_RIGHT:
            self.agent_headings[agent_id] = (self.agent_headings[agent_id] + 20.0) % 360.0
        elif action == ACCELERATE:
            self.agent_speeds[agent_id] = min(12.0, self.agent_speeds[agent_id] + 0.5)
        elif action == DECELERATE:
            self.agent_speeds[agent_id] = max(0.0, self.agent_speeds[agent_id] - 0.5)
        elif action == HOLD:
            self.agent_speeds[agent_id] = 0.0

        rad = math.radians(self.agent_headings[agent_id])
        delta = np.array([math.cos(rad), math.sin(rad), 0.0], dtype=np.float32) * float(self.agent_speeds[agent_id])
        self.agent_positions[agent_id] = self.agent_positions[agent_id] + delta
        self.agent_positions[agent_id] = np.clip(self.agent_positions[agent_id], 0.0, float(self.grid_size))

    def get_formation_score(self) -> float:
        """Evaluate station-keeping discipline for coordinated maneuver."""
        if len(self.agents) < 2:
            return 1.0
        distances: List[float] = []
        for i in range(len(self.agents)):
            for j in range(i + 1, len(self.agents)):
                a = self.agent_positions[self.agents[i]]
                b = self.agent_positions[self.agents[j]]
                distances.append(float(np.linalg.norm(a - b)))
        if not distances:
            return 1.0
        avg_distance = float(np.mean(distances))
        error = abs(avg_distance - self.target_spacing)
        return max(0.0, 1.0 - (error / max(self.target_spacing, 1.0)))

    def step(self, actions: Dict[str, int]):
        self.step_count += 1
        outputs: Dict[str, Tuple[Dict[str, np.ndarray], float, bool, bool, Dict[str, Any]]] = {}
        formation_bonus = 50.0 * self.get_formation_score()
        all_close_to_waypoint = True
        any_destroyed = False
        coordinated_avoidance = 0.0

        for agent_id in list(self.agents):
            action = int(actions.get(agent_id, HOLD))
            self._apply_action(agent_id, action)
            reward = -1.0
            terminated = False
            truncated = self.step_count >= self.max_steps
            info: Dict[str, Any] = {}

            nearest = self._nearest_threat(self.agent_positions[agent_id])
            if nearest < 8.0:
                self.agent_destroyed[agent_id] = True
                terminated = True
                reward -= 100.0
                any_destroyed = True
            elif nearest > 25.0:
                coordinated_avoidance += 5.0

            waypoint_distance = float(np.linalg.norm(self.mission_waypoint - self.agent_positions[agent_id]))
            all_close_to_waypoint = all_close_to_waypoint and waypoint_distance <= 12.0

            reward += formation_bonus / max(1, self.n_agents)
            outputs[agent_id] = (self._obs_for(agent_id), reward, terminated, truncated, info)

        collective_bonus = 200.0 if all_close_to_waypoint else 0.0
        avoidance_bonus = 20.0 if coordinated_avoidance >= (self.n_agents * 2.5) else 0.0

        for agent_id in outputs:
            obs, reward, terminated, truncated, info = outputs[agent_id]
            reward += collective_bonus / max(1, self.n_agents)
            reward += avoidance_bonus / max(1, self.n_agents)
            if any_destroyed:
                reward -= 100.0 / max(1, self.n_agents)
            outputs[agent_id] = (obs, float(reward), terminated or all_close_to_waypoint, truncated, info)

        return outputs

