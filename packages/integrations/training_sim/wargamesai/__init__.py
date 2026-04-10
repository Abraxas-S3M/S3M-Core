"""S3M training_sim integration wrapper for WargamesAI."""

from __future__ import annotations

import importlib

WargamesaiAdapter = importlib.import_module(
    "packages.integrations.training_sim.wargamesai.adapter"
).WargamesaiAdapter

__all__ = ["WargamesaiAdapter"]
