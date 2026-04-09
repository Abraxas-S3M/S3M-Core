"""rpg_mpc navigation integration package."""

try:
    from .adapter import RpgMpcAdapter
except ImportError:
    import importlib

    RpgMpcAdapter = importlib.import_module(
        "packages.integrations.navigation.rpg-mpc.adapter"
    ).RpgMpcAdapter

__all__ = ["RpgMpcAdapter"]
