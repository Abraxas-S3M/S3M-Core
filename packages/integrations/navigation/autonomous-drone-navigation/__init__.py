"""Autonomous-drone-navigation navigation integration adapter for S3M."""

from __future__ import annotations

import importlib

AutonomousDroneNavigationAdapter = importlib.import_module(
    "packages.integrations.navigation.autonomous-drone-navigation.adapter"
).AutonomousDroneNavigationAdapter

__all__ = ["AutonomousDroneNavigationAdapter"]
