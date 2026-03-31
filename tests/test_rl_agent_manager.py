#!/usr/bin/env python3
"""Tests for RLAgentManager tactical backend handling."""

from __future__ import annotations

from src.autonomy.rl.agent_manager import RLAgentManager
from src.autonomy.rl.environments import MilitaryEnvironment


def test_rl_manager_initialization_detects_backend():
    mgr = RLAgentManager(backend="auto")
    assert mgr.backend_name in {"rllib", "sb3", "builtin"}


def test_builtin_fallback_create_agent_and_predict():
    mgr = RLAgentManager(backend="builtin")
    env = MilitaryEnvironment(grid_size=100, max_steps=30, n_threats=2)
    agent_id = mgr.create_agent(env=env, algorithm="PPO")
    obs, _ = env.reset(seed=42)
    action = mgr.predict(agent_id, obs)
    assert isinstance(action, int)
    assert 0 <= action < 7


def test_train_returns_metrics():
    mgr = RLAgentManager(backend="builtin")
    env = MilitaryEnvironment(grid_size=100, max_steps=20, n_threats=2)
    agent_id = mgr.create_agent(env=env, algorithm="PPO")
    metrics = mgr.train(agent_id, n_steps=100)
    assert "mean_reward" in metrics
    assert "episodes" in metrics
    assert "steps" in metrics


def test_evaluate_returns_mean_reward():
    mgr = RLAgentManager(backend="builtin")
    env = MilitaryEnvironment(grid_size=100, max_steps=20, n_threats=2)
    agent_id = mgr.create_agent(env=env, algorithm="PPO")
    mgr.train(agent_id, n_steps=80)
    report = mgr.evaluate(agent_id, n_episodes=2)
    assert "mean_reward" in report
    assert "std_reward" in report


def test_health_check_structure():
    mgr = RLAgentManager(backend="builtin")
    health = mgr.health_check()
    assert "backend" in health
    assert "active_agents" in health
    assert "policies_on_disk" in health
