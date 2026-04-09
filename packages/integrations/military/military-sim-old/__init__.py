"""S3M military integration wrapper for military-sim-old."""

from __future__ import annotations

import importlib

MilitarySimOldAdapter = importlib.import_module(
    "packages.integrations.military.military-sim-old.adapter"
).MilitarySimOldAdapter

__all__ = ["MilitarySimOldAdapter"]
