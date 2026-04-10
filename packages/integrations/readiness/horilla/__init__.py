"""S3M readiness integration wrapper for horilla."""

from __future__ import annotations

import importlib.util
from pathlib import Path
from typing import Any

_CLASS_NAME = "HorillaAdapter"


def __getattr__(name: str) -> Any:
    """Lazily expose adapter class for unconventional slug package paths."""
    if name != _CLASS_NAME:
        raise AttributeError(f"module {__name__} has no attribute {name}")

    adapter_path = Path(__file__).resolve().parent / "adapter.py"
    spec = importlib.util.spec_from_file_location(f"{__name__}.adapter", adapter_path)
    if spec is None or spec.loader is None:
        raise ImportError(f"Unable to load adapter module from {adapter_path}")

    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return getattr(module, _CLASS_NAME)


__all__ = [_CLASS_NAME]
