
"""ego-planner-swarm integration package."""

try:
    from .adapter import EgoPlannerSwarmAdapter
except ImportError:
    import importlib

    EgoPlannerSwarmAdapter = importlib.import_module(
        "packages.integrations.swarm.ego-planner-swarm.adapter"
    ).EgoPlannerSwarmAdapter

__all__ = ["EgoPlannerSwarmAdapter"]
