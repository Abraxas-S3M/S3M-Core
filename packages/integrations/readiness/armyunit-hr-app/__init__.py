"""ArmyUnit-HR-App readiness integration adapter for S3M."""

from __future__ import annotations

import importlib

ArmyunitHrAppAdapter = importlib.import_module(
    "packages.integrations.readiness.armyunit-hr-app.adapter"
).ArmyunitHrAppAdapter

__all__ = ["ArmyunitHrAppAdapter"]
