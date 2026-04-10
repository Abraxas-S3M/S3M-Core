"""Autonomous-drone-navigation (variants) integration package."""

try:
    from .adapter import AutonomousDroneNavigationvariantsAdapter
except ImportError:
    import importlib

    AutonomousDroneNavigationvariantsAdapter = importlib.import_module(
        "packages.integrations.navigation.autonomous-drone-navigation-variants.adapter"
    ).AutonomousDroneNavigationvariantsAdapter

__all__ = ["AutonomousDroneNavigationvariantsAdapter"]
