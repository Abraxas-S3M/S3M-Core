"""OMPL navigation integration package."""

try:
    from .adapter import OmplAdapter
except ImportError:
    import importlib

    OmplAdapter = importlib.import_module(
        "packages.integrations.navigation.ompl.adapter"
    ).OmplAdapter

__all__ = ["OmplAdapter"]
