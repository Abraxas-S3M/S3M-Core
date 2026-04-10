"""vswarm swarm integration package."""

from __future__ import annotations

import importlib

VswarmAdapter = importlib.import_module(
    "packages.integrations.swarm.vswarm.adapter"
).VswarmAdapter

__all__ = ["VswarmAdapter"]
