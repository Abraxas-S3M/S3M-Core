#!/usr/bin/env python3
"""Tests for tactical RL environments and reward functions."""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.autonomy.rl.environments import (
    ACCELERATE,
    DECELERATE,
    ENGAGE,
    HOLD,
    MOVE_FORWARD,
    TURN_LEFT,
    TURN_RIGHT,
    DroneSwarmEnv,
    MilitaryEnvironment,
)
from src.autonomy.rl.reward_functions import (
    formation_cohesion_reward,
    mission_completion_reward,
    threat_avoidance_reward,
)


def test_military_environment_reset_returns_valid_observation():
    env = MilitaryEnvironment(grid_size=50, max_steps=20, n_threats=3)
    obs, info = env.reset(seed=42)
    assert "agent_position" in obs
    assert obs["agent_position"].shape == (3,)
    assert obs["threat_positions"].shape == (3, 3)
    assert isinstance(info, dict)


def test_military_environment_step_all_actions():
    env = MilitaryEnvironment(grid_size=60, max_steps=10, n_threats=2)
    env.reset(seed=1)
    for action in [MOVE_FORWARD, TURN_LEFT, TURN_RIGHT, ACCELERATE, DECELERATE, ENGAGE, HOLD]:
        result = env.step(action)
        assert len(result) == 5
        obs, reward, terminated, truncated, info = result
        assert "agent_position" in obs
        assert isinstance(reward, float)
        assert isinstance(terminated, bool)
        assert isinstance(truncated, bool)
        assert isinstance(info, dict)


def test_drone_swarm_env_with_four_agents():
    env = DroneSwarmEnv(n_agents=4, grid_size=80, max_steps=20, n_threats=3)
    observations, infos = env.reset(seed=7)
    assert len(observations) == 4
    assert len(infos) == 4
    actions = {agent_id: MOVE_FORWARD for agent_id in observations}
    outputs = env.step(actions)
    assert len(outputs) == 4
    for agent_id, payload in outputs.items():
        obs, reward, terminated, truncated, info = payload
        assert agent_id in observations
        assert "agent_position" in obs
        assert isinstance(reward, float)
        assert isinstance(terminated, bool)
        assert isinstance(truncated, bool)
        assert isinstance(info, dict)


def test_reward_functions_individual():
    assert mission_completion_reward(5.0, threshold=10.0) >= 100.0
    assert threat_avoidance_reward(100.0, safe_distance=50.0) > 0
    cohesion = formation_cohesion_reward(
        {
            "a": (0.0, 0.0, 0.0),
            "b": (20.0, 0.0, 0.0),
            "c": (40.0, 0.0, 0.0),
        },
        target_spacing=20.0,
    )
    assert cohesion > 0
