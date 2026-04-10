"""python-battlesim simulation integration adapter for S3M."""

from __future__ import annotations

import importlib

PythonBattlesimAdapter = importlib.import_module(
    "packages.integrations.simulation.python-battlesim.adapter"
).PythonBattlesimAdapter

__all__ = ["PythonBattlesimAdapter"]
