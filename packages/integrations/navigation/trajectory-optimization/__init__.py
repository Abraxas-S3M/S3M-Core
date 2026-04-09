"""trajectory_optimization navigation integration adapter for S3M."""

from __future__ import annotations

import importlib

TrajectoryOptimizationAdapter = importlib.import_module(
    "packages.integrations.navigation.trajectory-optimization.adapter"
).TrajectoryOptimizationAdapter

__all__ = ["TrajectoryOptimizationAdapter"]
