"""Multi-Robot-Coordination-Framework swarm integration adapter package for S3M."""

try:
    from .adapter import MultiRobotCoordinationFrameworkAdapter
except ImportError:
    import importlib

    MultiRobotCoordinationFrameworkAdapter = importlib.import_module(
        "packages.integrations.swarm.multi-robot-coordination-framework.adapter"
    ).MultiRobotCoordinationFrameworkAdapter

__all__ = ["MultiRobotCoordinationFrameworkAdapter"]

