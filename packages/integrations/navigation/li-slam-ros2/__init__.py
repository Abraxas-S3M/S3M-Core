"""li_slam_ros2 navigation integration adapter for S3M."""

from __future__ import annotations

import importlib

LiSlamRos2Adapter = importlib.import_module(
    "packages.integrations.navigation.li-slam-ros2.adapter"
).LiSlamRos2Adapter

__all__ = ["LiSlamRos2Adapter"]
