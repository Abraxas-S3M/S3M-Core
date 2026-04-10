"""meshtastic integration package."""

try:
    from .adapter import MeshtasticAdapter
except ImportError:
    import importlib

    MeshtasticAdapter = importlib.import_module(
        "packages.integrations.comms.meshtastic.adapter"
    ).MeshtasticAdapter

__all__ = ["MeshtasticAdapter"]
