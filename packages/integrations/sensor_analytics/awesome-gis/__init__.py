"""awesome-gis sensor analytics integration for S3M."""

from __future__ import annotations

import importlib

AwesomeGisAdapter = importlib.import_module(
    "packages.integrations.sensor_analytics.awesome-gis.adapter"
).AwesomeGisAdapter

__all__ = ["AwesomeGisAdapter"]
