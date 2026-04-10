"""custom-scripts sensor analytics integration for S3M."""

from __future__ import annotations

import importlib

CustomScriptsAdapter = importlib.import_module(
    "packages.integrations.sensor_analytics.custom-scripts.adapter"
).CustomScriptsAdapter

__all__ = ["CustomScriptsAdapter"]
