"""UAVSwarm-dataset sensor-fusion integration adapter for S3M."""

from __future__ import annotations

import importlib

UavswarmDatasetAdapter = importlib.import_module(
    "packages.integrations.sensor_fusion.uavswarm-dataset.adapter"
).UavswarmDatasetAdapter

__all__ = ["UavswarmDatasetAdapter"]
