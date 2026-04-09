"""Detectron2 object detection integration adapter for S3M."""

from __future__ import annotations

import importlib

Detectron2objectDetectionAdapter = importlib.import_module(
    "packages.integrations.nato.detectron2-object-detection.adapter"
).Detectron2objectDetectionAdapter

__all__ = ["Detectron2objectDetectionAdapter"]
