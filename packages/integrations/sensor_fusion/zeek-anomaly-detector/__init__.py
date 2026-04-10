"""zeek_anomaly_detector sensor-fusion integration adapter for S3M."""

from __future__ import annotations

import importlib

ZeekAnomalyDetectorAdapter = importlib.import_module(
    "packages.integrations.sensor_fusion.zeek-anomaly-detector.adapter"
).ZeekAnomalyDetectorAdapter

__all__ = ["ZeekAnomalyDetectorAdapter"]
