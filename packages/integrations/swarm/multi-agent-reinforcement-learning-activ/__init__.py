"""multi-agent-reinforcement-learning-active-slam swarm integration package."""

try:
    from .adapter import MultiAgentReinforcementLearningAdapter
except ImportError:
    import importlib

    MultiAgentReinforcementLearningAdapter = importlib.import_module(
        "packages.integrations.swarm.multi-agent-reinforcement-learning-activ.adapter"
    ).MultiAgentReinforcementLearningAdapter

__all__ = ["MultiAgentReinforcementLearningAdapter"]
