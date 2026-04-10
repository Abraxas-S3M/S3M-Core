"""Border-Surveillance-System integration package."""

from __future__ import annotations

import importlib.util
from pathlib import Path

try:
    from .adapter import BorderSurveillanceSystemAdapter
except ImportError:
    _ADAPTER_PATH = Path(__file__).resolve().parent / "adapter.py"
    _SPEC = importlib.util.spec_from_file_location(
        "s3m_sensor_analytics_border_surveillance_system_adapter",
        _ADAPTER_PATH,
    )
    if _SPEC is None or _SPEC.loader is None:
        raise ImportError(f"Unable to load adapter from {_ADAPTER_PATH}")
    _MODULE = importlib.util.module_from_spec(_SPEC)
    _SPEC.loader.exec_module(_MODULE)
    BorderSurveillanceSystemAdapter = _MODULE.BorderSurveillanceSystemAdapter

__all__ = ["BorderSurveillanceSystemAdapter"]
