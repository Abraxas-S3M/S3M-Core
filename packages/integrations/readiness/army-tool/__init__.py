"""Army-Tool readiness integration adapter for S3M."""

from __future__ import annotations

import importlib

ArmyToolAdapter = importlib.import_module(
    "packages.integrations.readiness.army-tool.adapter"
).ArmyToolAdapter

__all__ = ["ArmyToolAdapter"]
