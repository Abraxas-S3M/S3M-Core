"""sumo-search-for-unidentified-maritime-ob integration for S3M."""

from __future__ import annotations

import importlib

SumosearchForUnidentifiedAdapter = importlib.import_module(
    "packages.integrations.sensor_analytics.sumo-search-for-unidentified-maritime-ob.adapter"
).SumosearchForUnidentifiedAdapter

__all__ = ["SumosearchForUnidentifiedAdapter"]
