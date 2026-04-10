"""Smart Track sensor-fusion integration wrapper for S3M."""

from __future__ import annotations

import importlib

SmartTrackAdapter = importlib.import_module(
    "packages.integrations.sensor_fusion.smart-track.adapter"
).SmartTrackAdapter

__all__ = ["SmartTrackAdapter"]
