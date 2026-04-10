"""UAV-orchestrator swarm integration adapter package for S3M."""

try:
    from .adapter import UavOrchestratorAdapter
except ImportError:
    import importlib

    UavOrchestratorAdapter = importlib.import_module(
        "packages.integrations.swarm.uav-orchestrator.adapter"
    ).UavOrchestratorAdapter

__all__ = ["UavOrchestratorAdapter"]

