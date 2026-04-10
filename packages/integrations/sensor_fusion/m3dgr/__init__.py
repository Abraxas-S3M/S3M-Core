"""M3DGR sensor-fusion integration adapter for S3M."""

from __future__ import annotations

import importlib

M3dgrAdapter = importlib.import_module(
    "packages.integrations.sensor_fusion.m3dgr.adapter"
).M3dgrAdapter

__all__ = ["M3dgrAdapter"]
