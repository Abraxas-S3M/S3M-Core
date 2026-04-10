"""Satellite-Imagery-Datasets-Containing-Ships integration package."""

from __future__ import annotations

import importlib.util
from pathlib import Path

try:
    from .adapter import SatelliteImageryDatasetsContainingAdapter
except ImportError:
    _ADAPTER_PATH = Path(__file__).resolve().parent / "adapter.py"
    _SPEC = importlib.util.spec_from_file_location(
        "s3m_sensor_analytics_satellite_imagery_datasets_containing_sh_adapter",
        _ADAPTER_PATH,
    )
    if _SPEC is None or _SPEC.loader is None:
        raise ImportError(f"Unable to load adapter from {_ADAPTER_PATH}")
    _MODULE = importlib.util.module_from_spec(_SPEC)
    _SPEC.loader.exec_module(_MODULE)
    SatelliteImageryDatasetsContainingAdapter = _MODULE.SatelliteImageryDatasetsContainingAdapter

__all__ = ["SatelliteImageryDatasetsContainingAdapter"]
