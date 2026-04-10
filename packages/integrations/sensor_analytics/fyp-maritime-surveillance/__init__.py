"""FYP-Maritime_Surveillance integration package."""

from __future__ import annotations

import importlib.util
from pathlib import Path

try:
    from .adapter import FypMaritimeSurveillanceAdapter
except ImportError:
    _ADAPTER_PATH = Path(__file__).resolve().parent / "adapter.py"
    _SPEC = importlib.util.spec_from_file_location(
        "s3m_sensor_analytics_fyp_maritime_surveillance_adapter",
        _ADAPTER_PATH,
    )
    if _SPEC is None or _SPEC.loader is None:
        raise ImportError(f"Unable to load adapter from {_ADAPTER_PATH}")
    _MODULE = importlib.util.module_from_spec(_SPEC)
    _SPEC.loader.exec_module(_MODULE)
    FypMaritimeSurveillanceAdapter = _MODULE.FypMaritimeSurveillanceAdapter

__all__ = ["FypMaritimeSurveillanceAdapter"]
