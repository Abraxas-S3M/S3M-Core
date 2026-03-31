"""ATR integration for drone operations domain app."""

from __future__ import annotations

from collections import Counter
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from src.threat_detection.models import ThreatLevel
from src.threat_detection.object_detector import ObjectDetector
from src.threat_detection.threat_manager import ThreatManager

from src.apps._shared import normalize_coords, utc_now_iso


class ATRIntegrator:
    """Bridge object detection outputs into tactical threat workflow."""

    def __init__(self) -> None:
        self.detector = ObjectDetector(model_path="models/yolov8n-military.pt")
        self.threat_manager = ThreatManager()
        self._history: List[dict] = []
        self._stats = {"total_detections": 0, "by_class": Counter(), "threats_generated": 0}

    def _threat_level_from_detection(self, detection: dict) -> str:
        name = str(detection.get("class", "")).lower()
        if any(k in name for k in ("missile", "jet", "aircraft")):
            return "CRITICAL"
        if any(k in name for k in ("tank", "rifle", "helicopter", "warship")):
            return "HIGH"
        if any(k in name for k in ("soldier", "truck")):
            return "MEDIUM"
        return "LOW"

    def process_frame(self, image_path_or_array, agent_position: tuple = None) -> dict:
        location = normalize_coords(agent_position, dims=3, default=(0.0, 0.0, 0.0))
        detections_raw = self.detector.detect(image_path_or_array)
        detections = []
        highest = "LOW"
        threat_events = []
        for det in detections_raw:
            level = self._threat_level_from_detection({"class": det.class_name})
            detection = {
                "class": det.class_name,
                "confidence": float(det.confidence),
                "bbox": tuple(det.bbox_xyxy),
                "threat_level": level,
            }
            detections.append(detection)
            self._stats["by_class"][det.class_name] += 1
            if ThreatLevel.from_value(level) > ThreatLevel.from_value(highest):
                highest = level

        if detections:
            try:
                threat_events = self.detector.detect_to_threats(
                    image_path=image_path_or_array if isinstance(image_path_or_array, str) else "in_memory_frame",
                    location={"x": location[0], "y": location[1], "z": location[2]},
                )
                for event in threat_events:
                    self.threat_manager._threat_log.append(event)  # thin ingestion fallback for missing API
            except Exception:
                threat_events = []

        self._stats["total_detections"] += len(detections)
        self._stats["threats_generated"] += len(threat_events)
        entry = {
            "timestamp": utc_now_iso(),
            "position": location,
            "detections": detections,
            "highest_threat_level": highest,
        }
        self._history.append(entry)
        self._history = self._history[-500:]

        return {
            "detections": detections,
            "threats_generated": len(threat_events),
            "highest_threat_level": highest,
            "replan_recommended": self.should_replan(detections),
            "timestamp": utc_now_iso(),
        }

    def should_replan(self, detections: List[dict]) -> bool:
        for det in detections:
            confidence = float(det.get("confidence", 0.0))
            level = str(det.get("threat_level", "LOW")).upper()
            if confidence > 0.7 and ThreatLevel.from_value(level) >= ThreatLevel.HIGH:
                return True
        return False

    def get_detection_history(self, limit: int = 50) -> List[dict]:
        if not isinstance(limit, int) or limit <= 0:
            raise ValueError("limit must be a positive integer")
        return list(self._history[-limit:])

    def get_stats(self) -> dict:
        return {
            "total_detections": self._stats["total_detections"],
            "by_class": dict(self._stats["by_class"]),
            "threats_generated": self._stats["threats_generated"],
        }
