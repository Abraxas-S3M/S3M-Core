
"""PX4_Swarm_Controller integration package."""

try:
    from .adapter import Px4SwarmControllerAdapter
except ImportError:
    import importlib

    Px4SwarmControllerAdapter = importlib.import_module(
        "packages.integrations.swarm.px4-swarm-controller.adapter"
    ).Px4SwarmControllerAdapter

__all__ = ["Px4SwarmControllerAdapter"]
