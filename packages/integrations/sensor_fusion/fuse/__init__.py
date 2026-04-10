"""fuse integration package."""

try:
    from .adapter import FuseAdapter
except ImportError:
    import importlib

    FuseAdapter = importlib.import_module("packages.integrations.sensor_fusion.fuse.adapter").FuseAdapter

__all__ = ["FuseAdapter"]
