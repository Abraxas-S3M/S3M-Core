"""VisionUAV-Navigation integration package."""

try:
    from .adapter import VisionuavNavigationAdapter
except ImportError:
    import importlib

    VisionuavNavigationAdapter = importlib.import_module(
        "packages.integrations.navigation.visionuav-navigation.adapter"
    ).VisionuavNavigationAdapter

__all__ = ["VisionuavNavigationAdapter"]
