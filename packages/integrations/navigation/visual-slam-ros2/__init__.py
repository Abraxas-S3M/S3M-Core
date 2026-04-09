"""visual-slam-ros2 navigation integration adapter for S3M."""

from __future__ import annotations

import importlib

VisualSlamRos2Adapter = importlib.import_module(
    "packages.integrations.navigation.visual-slam-ros2.adapter"
).VisualSlamRos2Adapter

__all__ = ["VisualSlamRos2Adapter"]
