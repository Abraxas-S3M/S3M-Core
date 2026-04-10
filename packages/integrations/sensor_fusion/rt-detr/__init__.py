"""rt-detr integration package."""

from __future__ import annotations

import importlib

RtDetrAdapter = importlib.import_module(
    "packages.integrations.sensor_fusion.rt-detr.adapter"
).RtDetrAdapter

__all__ = ["RtDetrAdapter"]
