
"""boomslang-c2-sim integration package."""

try:
    from .adapter import BoomslangC2SimAdapter
except ImportError:
    import importlib

    BoomslangC2SimAdapter = importlib.import_module(
        "packages.integrations.swarm.boomslang-c2-sim.adapter"
    ).BoomslangC2SimAdapter

__all__ = ["BoomslangC2SimAdapter"]
