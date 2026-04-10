"""multi_robot_ros2 swarm integration package."""

from __future__ import annotations

import importlib

MultiRobotRos2Adapter = importlib.import_module(
    "packages.integrations.swarm.multi-robot-ros2.adapter"
).MultiRobotRos2Adapter

__all__ = ["MultiRobotRos2Adapter"]
