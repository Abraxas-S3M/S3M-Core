"""Reinforcement learning interfaces for tactical autonomy training."""

from .agent_manager import RLAgentManager, RewardConfig
from .environments import MilitaryEnvironment, DroneSwarmEnv
from .policy_registry import PolicyRegistry

__all__ = [
    "RLAgentManager",
    "MilitaryEnvironment",
    "DroneSwarmEnv",
    "PolicyRegistry",
    "RewardConfig",
]
