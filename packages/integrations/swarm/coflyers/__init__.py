"""CoFlyers swarm integration package."""

from __future__ import annotations

import importlib

CoflyersAdapter = importlib.import_module(
    "packages.integrations.swarm.coflyers.adapter"
).CoflyersAdapter

__all__ = ["CoflyersAdapter"]
