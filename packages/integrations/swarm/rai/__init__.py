"""RAI swarm integration package."""

from __future__ import annotations

import importlib

RaiAdapter = importlib.import_module(
    "packages.integrations.swarm.rai.adapter"
).RaiAdapter

__all__ = ["RaiAdapter"]
