"""player-tool sensor analytics integration for S3M."""

from __future__ import annotations

import importlib

PlayerToolAdapter = importlib.import_module(
    "packages.integrations.sensor_analytics.player-tool.adapter"
).PlayerToolAdapter

__all__ = ["PlayerToolAdapter"]
