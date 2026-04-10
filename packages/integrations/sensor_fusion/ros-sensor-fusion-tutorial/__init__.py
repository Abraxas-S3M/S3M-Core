"""ros-sensor-fusion-tutorial integration adapter for S3M."""

from __future__ import annotations

import importlib

RosSensorFusionTutorialAdapter = importlib.import_module(
    "packages.integrations.sensor_fusion.ros-sensor-fusion-tutorial.adapter"
).RosSensorFusionTutorialAdapter

__all__ = ["RosSensorFusionTutorialAdapter"]
