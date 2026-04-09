"""nmpc_px4_ros2 navigation integration adapter for S3M."""

from __future__ import annotations

import importlib

NmpcPx4Ros2Adapter = importlib.import_module(
    "packages.integrations.navigation.nmpc-px4-ros2.adapter"
).NmpcPx4Ros2Adapter

__all__ = ["NmpcPx4Ros2Adapter"]
