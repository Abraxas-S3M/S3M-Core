"""drones-swarm integration adapter package for S3M."""

try:
    from .adapter import DronesSwarmAdapter
except ImportError:
    import importlib

    DronesSwarmAdapter = importlib.import_module(
        "packages.integrations.swarm.drones-swarm.adapter"
    ).DronesSwarmAdapter

__all__ = ["DronesSwarmAdapter"]

