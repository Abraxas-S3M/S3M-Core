"""drone_path_predictor_ros navigation integration adapter for S3M."""

from __future__ import annotations

import importlib

DronePathPredictorRosAdapter = importlib.import_module(
    "packages.integrations.navigation.drone-path-predictor-ros.adapter"
).DronePathPredictorRosAdapter

__all__ = ["DronePathPredictorRosAdapter"]
