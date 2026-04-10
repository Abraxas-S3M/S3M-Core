"""open-dis swarm integration package."""

try:
    from .adapter import OpenDisAdapter
except ImportError:
    import importlib

    OpenDisAdapter = importlib.import_module(
        "packages.integrations.swarm.open-dis.adapter"
    ).OpenDisAdapter

__all__ = ["OpenDisAdapter"]
