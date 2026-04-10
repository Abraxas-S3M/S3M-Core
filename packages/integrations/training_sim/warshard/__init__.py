"""S3M training_sim integration wrapper for warshard."""

from __future__ import annotations

import importlib

WarshardAdapter = importlib.import_module(
    "packages.integrations.training_sim.warshard.adapter"
).WarshardAdapter

__all__ = ["WarshardAdapter"]
