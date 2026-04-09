"""Battle Simulator military integration adapter for S3M."""

from __future__ import annotations

import importlib

BattleSimulatorAdapter = importlib.import_module(
    "packages.integrations.military.battle-simulator.adapter"
).BattleSimulatorAdapter

__all__ = ["BattleSimulatorAdapter"]
