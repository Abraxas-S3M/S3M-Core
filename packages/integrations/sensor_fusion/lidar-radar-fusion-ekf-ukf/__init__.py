"""lidar_radar_fusion_ekf_ukf sensor fusion integration adapter for S3M."""

from __future__ import annotations

import importlib

LidarRadarFusionEkfAdapter = importlib.import_module(
    "packages.integrations.sensor_fusion.lidar-radar-fusion-ekf-ukf.adapter"
).LidarRadarFusionEkfAdapter

__all__ = ["LidarRadarFusionEkfAdapter"]
