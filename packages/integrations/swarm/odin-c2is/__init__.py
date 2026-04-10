"""ODIN C2IS swarm integration package."""

try:
    from .adapter import Odinc2isAdapter
except ImportError:
    import importlib

    Odinc2isAdapter = importlib.import_module(
        "packages.integrations.swarm.odin-c2is.adapter"
    ).Odinc2isAdapter

__all__ = ["Odinc2isAdapter"]
