"""heterogeneous-swarm-robotics swarm integration adapter for S3M."""

from __future__ import annotations

import importlib

HeterogeneousSwarmRoboticsAdapter = importlib.import_module(
    "packages.integrations.swarm.heterogeneous-swarm-robotics.adapter"
).HeterogeneousSwarmRoboticsAdapter

__all__ = ["HeterogeneousSwarmRoboticsAdapter"]
