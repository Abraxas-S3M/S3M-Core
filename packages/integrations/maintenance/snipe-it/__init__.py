"""snipe-it maintenance integration adapter for S3M."""

from __future__ import annotations

import importlib

SnipeItAdapter = importlib.import_module(
    "packages.integrations.maintenance.snipe-it.adapter"
).SnipeItAdapter

__all__ = ["SnipeItAdapter"]
