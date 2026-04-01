"""Top-level manager for S3M Phase 15 sensor analytics workflows."""

from __future__ import annotations

from typing import Any, Dict, List

from services.sensor_analytics.dataset_manager import RemoteSensingDatasetManager
from services.sensor_analytics.fusion_engine import MaritimeFusionEngine
from services.sensor_analytics.models import MaritimePicture


class SensorAnalyticsManager:
    """Unified interface for Layer 09 maritime and border analytics tasks."""

    def __init__(self) -> None:
        self.fusion = MaritimeFusionEngine()
        self.datasets = RemoteSensingDatasetManager()

    def process_sar(self, image_path: str) -> Dict[str, Any]:
        return self.fusion.process_sar_image(image_path)

    def ingest_ais(self, filepath: str) -> Dict[str, Any]:
        self.fusion.ais_tracker.ingest_file(filepath)
        return {"status": "ingested", "vessels_tracked": len(self.fusion.ais_tracker.vessels)}

    def scan_borders(self) -> Dict[str, List[Dict[str, Any]]]:
        return {k: [a.to_dict() for a in v] for k, v in self.fusion.border_engine.scan_all_zones().items()}

    def get_maritime_picture(self) -> MaritimePicture:
        return self.fusion.get_maritime_picture()

    def get_dark_vessels(self) -> List[Dict[str, Any]]:
        return self.fusion.get_dark_vessels()

    def get_zone_status(self) -> Dict[str, Any]:
        zones = self.fusion.border_engine.zone_manager.get_zones()
        return {"zones": [z.to_dict() for z in zones], "total": len(zones)}

    def get_statistics(self) -> Dict[str, Any]:
        picture = self.get_maritime_picture()
        return {
            "vessels_tracked": len(picture.vessels),
            "sar_detections": len(self.fusion._unmatched_sar),
            "alerts": len(picture.border_alerts),
            "dark_vessels": picture.statistics.get("dark_vessels", 0),
        }

    def health_check(self) -> Dict[str, Any]:
        return {
            "fusion": self.fusion.health_check(),
            "datasets": self.datasets.health_check(),
        }
