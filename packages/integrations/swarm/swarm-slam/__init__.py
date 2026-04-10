"""Swarm-SLAM swarm integration adapter for S3M."""

from __future__ import annotations

import importlib

SwarmSlamAdapter = importlib.import_module(
    "packages.integrations.swarm.swarm-slam.adapter"
).SwarmSlamAdapter

__all__ = ["SwarmSlamAdapter"]
