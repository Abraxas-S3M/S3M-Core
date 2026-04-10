"""ultralytics-yolov8-yolo11 integration package."""

from __future__ import annotations

import importlib

Ultralyticsyolov8yolo11Adapter = importlib.import_module(
    "packages.integrations.sensor_fusion.ultralytics-yolov8-yolo11.adapter"
).Ultralyticsyolov8yolo11Adapter

__all__ = ["Ultralyticsyolov8yolo11Adapter"]
