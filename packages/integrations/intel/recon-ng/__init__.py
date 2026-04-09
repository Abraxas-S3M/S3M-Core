"""Recon-ng intel integration package."""

try:
    from .adapter import ReconNgAdapter
except ImportError:
    # Fallback supports test collection paths where this package is imported standalone.
    import importlib

    ReconNgAdapter = importlib.import_module(
        "packages.integrations.intel.recon-ng.adapter"
    ).ReconNgAdapter

__all__ = ["ReconNgAdapter"]
