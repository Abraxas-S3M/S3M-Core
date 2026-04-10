"""perception-vault integration package."""

from __future__ import annotations

import importlib

PerceptionVaultAdapter = importlib.import_module(
    "packages.integrations.sensor_fusion.perception-vault.adapter"
).PerceptionVaultAdapter

__all__ = ["PerceptionVaultAdapter"]
