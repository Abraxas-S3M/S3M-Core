"""Military-Simulator simulation integration adapter for S3M."""

from __future__ import annotations

import importlib

MilitarySimulatorAdapter = importlib.import_module(
    "packages.integrations.simulation.military-simulator.adapter"
).MilitarySimulatorAdapter

__all__ = ["MilitarySimulatorAdapter"]
