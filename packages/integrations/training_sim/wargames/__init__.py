"""S3M training_sim integration wrapper for Wargames."""

from __future__ import annotations

import importlib

WargamesAdapter = importlib.import_module(
    "packages.integrations.training_sim.wargames.adapter"
).WargamesAdapter

__all__ = ["WargamesAdapter"]
