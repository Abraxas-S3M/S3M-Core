"""awesome-radar-perception integration adapter for S3M."""

from __future__ import annotations

import importlib

AwesomeRadarPerceptionAdapter = importlib.import_module(
    "packages.integrations.sensor_fusion.awesome-radar-perception.adapter"
).AwesomeRadarPerceptionAdapter

__all__ = ["AwesomeRadarPerceptionAdapter"]
