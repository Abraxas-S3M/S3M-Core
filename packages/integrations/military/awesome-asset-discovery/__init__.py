"""Awesome-Asset-Discovery military integration package."""

try:
    from .adapter import AwesomeAssetDiscoveryAdapter
except ImportError:
    # Fallback supports direct module loading in test collection paths.
    import importlib.util
    from pathlib import Path

    _adapter_path = Path(__file__).resolve().parent / "adapter.py"
    _spec = importlib.util.spec_from_file_location(
        "s3m_military_awesome_asset_discovery_adapter",
        _adapter_path,
    )
    if _spec is None or _spec.loader is None:
        raise
    _module = importlib.util.module_from_spec(_spec)
    _spec.loader.exec_module(_module)
    AwesomeAssetDiscoveryAdapter = _module.AwesomeAssetDiscoveryAdapter

__all__ = ["AwesomeAssetDiscoveryAdapter"]
