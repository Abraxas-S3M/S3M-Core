"""Swarm-Formation swarm integration package."""

from __future__ import annotations

import importlib

SwarmFormationAdapter = importlib.import_module(
    "packages.integrations.swarm.swarm-formation.adapter"
).SwarmFormationAdapter

__all__ = ["SwarmFormationAdapter"]
