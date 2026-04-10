"""inertialsense_ros2 navigation integration adapter for S3M."""

from __future__ import annotations

import importlib

InertialsenseRos2Adapter = importlib.import_module(
    "packages.integrations.navigation.inertialsense-ros2.adapter"
).InertialsenseRos2Adapter

__all__ = ["InertialsenseRos2Adapter"]
