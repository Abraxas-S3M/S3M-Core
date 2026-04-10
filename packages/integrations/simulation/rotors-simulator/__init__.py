"""rotors_simulator integration adapter for S3M simulation workflows."""

from __future__ import annotations

import importlib

RotorsSimulatorAdapter = importlib.import_module(
    "packages.integrations.simulation.rotors-simulator.adapter"
).RotorsSimulatorAdapter

__all__ = ["RotorsSimulatorAdapter"]
