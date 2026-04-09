"""drone_swarm military integration package."""

from __future__ import annotations

import importlib

DroneSwarmAdapter = importlib.import_module(
    "packages.integrations.military.drone-swarm.adapter"
).DroneSwarmAdapter

__all__ = ["DroneSwarmAdapter"]
