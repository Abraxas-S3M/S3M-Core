"""ROS2-NMPC-ACADOS navigation integration adapter for S3M."""

from __future__ import annotations

import importlib

Ros2NmpcAcadosAdapter = importlib.import_module(
    "packages.integrations.navigation.ros2-nmpc-acados.adapter"
).Ros2NmpcAcadosAdapter

__all__ = ["Ros2NmpcAcadosAdapter"]
