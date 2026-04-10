"""OpenC2SIM/C2SIMArtifacts swarm integration package."""

try:
    from .adapter import Openc2simC2simartifactsAdapter
except ImportError:
    import importlib

    Openc2simC2simartifactsAdapter = importlib.import_module(
        "packages.integrations.swarm.openc2sim---c2simartifacts.adapter"
    ).Openc2simC2simartifactsAdapter

__all__ = ["Openc2simC2simartifactsAdapter"]
