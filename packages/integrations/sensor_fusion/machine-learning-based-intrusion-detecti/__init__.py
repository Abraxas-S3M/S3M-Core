"""Machine-Learning-Based-Intrusion-Detection-System adapter for S3M."""

from __future__ import annotations

import importlib

MachineLearningBasedIntrusionAdapter = importlib.import_module(
    "packages.integrations.sensor_fusion.machine-learning-based-intrusion-detecti.adapter"
).MachineLearningBasedIntrusionAdapter

__all__ = ["MachineLearningBasedIntrusionAdapter"]
