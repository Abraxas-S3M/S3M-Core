"""awesome-geospatial sensor analytics integration for S3M."""

from __future__ import annotations

import importlib

AwesomeGeospatialAdapter = importlib.import_module(
    "packages.integrations.sensor_analytics.awesome-geospatial.adapter"
).AwesomeGeospatialAdapter

__all__ = ["AwesomeGeospatialAdapter"]
