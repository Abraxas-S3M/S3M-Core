"""Open mSupply maintenance integration wrapper for S3M."""

from __future__ import annotations

import importlib

OpenMsupplyAdapter = importlib.import_module(
    "packages.integrations.maintenance.open-msupply.adapter"
).OpenMsupplyAdapter

__all__ = ["OpenMsupplyAdapter"]
