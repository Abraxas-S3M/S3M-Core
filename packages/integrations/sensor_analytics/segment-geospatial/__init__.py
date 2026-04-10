"""segment-geospatial sensor analytics integration for S3M."""

from __future__ import annotations

import importlib

SegmentGeospatialAdapter = importlib.import_module(
    "packages.integrations.sensor_analytics.segment-geospatial.adapter"
).SegmentGeospatialAdapter

__all__ = ["SegmentGeospatialAdapter"]
