"""S3M military integration wrapper for Snipe-IT."""

from __future__ import annotations

import importlib

SnipeItAdapter = importlib.import_module(
    "packages.integrations.military.snipe-it.adapter"
).SnipeItAdapter

__all__ = ["SnipeItAdapter"]
