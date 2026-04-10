"""sensor-fusion integration adapter for S3M."""

from __future__ import annotations

import importlib

SensorFusionAdapter = importlib.import_module(
    "packages.integrations.sensor_fusion.sensor-fusion.adapter"
).SensorFusionAdapter

__all__ = ["SensorFusionAdapter"]
