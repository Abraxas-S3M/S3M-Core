"""eo-learn sensor analytics integration for S3M."""

from __future__ import annotations

import importlib

EoLearnAdapter = importlib.import_module(
    "packages.integrations.sensor_analytics.eo-learn.adapter"
).EoLearnAdapter

__all__ = ["EoLearnAdapter"]
