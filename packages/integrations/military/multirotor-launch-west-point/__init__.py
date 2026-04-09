"""West Point multirotor launch integration adapter for S3M."""

from __future__ import annotations

import importlib

MultirotorLaunchwestPointAdapter = importlib.import_module(
    "packages.integrations.military.multirotor-launch-west-point.adapter"
).MultirotorLaunchwestPointAdapter

__all__ = ["MultirotorLaunchwestPointAdapter"]
