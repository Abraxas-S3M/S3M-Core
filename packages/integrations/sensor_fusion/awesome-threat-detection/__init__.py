"""Awesome Threat Detection sensor-fusion integration wrapper for S3M."""

from __future__ import annotations

import importlib

AwesomeThreatDetectionAdapter = importlib.import_module(
    "packages.integrations.sensor_fusion.awesome-threat-detection.adapter"
).AwesomeThreatDetectionAdapter

__all__ = ["AwesomeThreatDetectionAdapter"]
