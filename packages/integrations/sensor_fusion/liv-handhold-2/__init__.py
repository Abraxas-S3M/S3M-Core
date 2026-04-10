"""LIV_handhold_2 sensor-fusion integration adapter for S3M."""

from __future__ import annotations

import importlib

LivHandhold2Adapter = importlib.import_module(
    "packages.integrations.sensor_fusion.liv-handhold-2.adapter"
).LivHandhold2Adapter

__all__ = ["LivHandhold2Adapter"]
