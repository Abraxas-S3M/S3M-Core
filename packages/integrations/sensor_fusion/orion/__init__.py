"""Orion sensor-fusion integration wrapper for S3M."""

from __future__ import annotations

import importlib

OrionAdapter = importlib.import_module(
    "packages.integrations.sensor_fusion.orion.adapter"
).OrionAdapter

__all__ = ["OrionAdapter"]
