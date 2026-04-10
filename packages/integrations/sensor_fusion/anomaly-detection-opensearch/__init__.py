"""OpenSearch anomaly-detection sensor-fusion adapter for S3M."""

from __future__ import annotations

import importlib

AnomalyDetectionopensearchAdapter = importlib.import_module(
    "packages.integrations.sensor_fusion.anomaly-detection-opensearch.adapter"
).AnomalyDetectionopensearchAdapter

__all__ = ["AnomalyDetectionopensearchAdapter"]
