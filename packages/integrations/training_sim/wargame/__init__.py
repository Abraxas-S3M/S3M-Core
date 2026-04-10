"""S3M training_sim integration wrapper for Wargame."""

from __future__ import annotations

import importlib

WargameAdapter = importlib.import_module(
    "packages.integrations.training_sim.wargame.adapter"
).WargameAdapter

__all__ = ["WargameAdapter"]
