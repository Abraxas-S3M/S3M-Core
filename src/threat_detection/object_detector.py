"""YOLOv8 object detection adapter for tactical target recognition."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import logging
import os
from typing import Any, Dict, List, Optional, Sequence, Tuple

from src.threat_detection.models import ThreatCategory, ThreatEvent, ThreatLevel, ThreatSource

LOGGER = logging.getLogger(__name__)


@dataclass
class Detection:
    """Single object detection result used by threat conversion pipeline."""

    class_name: str
    confidence: float
    bbox_xyxy: Tuple[float, float, float, float]
    class_id: int


class ObjectDetector:
    """Object detector wrapper for local YOLOv8/TensorRT military models."""

    DEFAULT_CLASS_LEVELS = {
        "tank": ThreatLevel.HIGH,
        "aircraft": ThreatLevel.CRITICAL,
        "soldier": ThreatLevel.MEDIUM,
        "rifle": ThreatLevel.HIGH,
        "missile": ThreatLevel.CRITICAL,
        "warship": ThreatLevel.HIGH,
        "helicopter": ThreatLevel.HIGH,
        "truck": ThreatLevel.LOW,
        "jet": ThreatLevel.CRITICAL,
    }

    KINETIC_CLASSES = {"tank", "aircraft", "rifle", "missile", "warship", "helicopter", "truck", "jet"}
    SURVEILLANCE_CLASSES = {"soldier"}

    def __init__(self, model_path: str, confidence_threshold: float = 0.5, device: str = "cuda") -> None:
        if not isinstance(model_path, str) or not model_path.strip():
            raise ValueError("model_path must be a non-empty string")
        if not isinstance(confidence_threshold, (int, float)) or not (0.0 <= float(confidence_threshold) <= 1.0):
            raise ValueError("confidence_threshold must be between 0.0 and 1.0")
        if not isinstance(device, str) or not device.strip():
            raise ValueError("device must be a non-empty string")

        self.model_path = model_path
        self.confidence_threshold = float(confidence_threshold)
        self.device = device
        self.model = None
        self.stub_mode = True
        self.available_classes = list(self.DEFAULT_CLASS_LEVELS.keys())

        try:
            from ultralytics import YOLO  # type: ignore

            if os.path.exists(self.model_path):
                self.model = YOLO(self.model_path)
                self.stub_mode = False
                try:
                    names = getattr(self.model, "names", None)
                    if isinstance(names, dict):
                        self.available_classes = [str(v) for v in names.values()]
                except Exception:
                    LOGGER.warning("Failed reading YOLO class names; using defaults")
            else:
                LOGGER.warning("YOLO model path not found. Running in stub mode: %s", self.model_path)
        except Exception:
            LOGGER.warning("ultralytics not installed/unavailable. Running in stub mode.")

    def detect(self, image_path_or_array: Any) -> List[Detection]:
        """Run detection and return normalized Detection objects."""
        if isinstance(image_path_or_array, str):
            if not image_path_or_array.strip():
                raise ValueError("image_path_or_array string path cannot be empty")
            if not self.stub_mode and not os.path.exists(image_path_or_array):
                raise FileNotFoundError(f"Image not found: {image_path_or_array}")
        elif image_path_or_array is None:
            raise ValueError("image_path_or_array cannot be None")

        if self.stub_mode:
            # Tactical stub keeps pipeline functional in disconnected test environments.
            return [
                Detection(
                    class_name="[STUB] soldier",
                    confidence=0.61,
                    bbox_xyxy=(100.0, 80.0, 220.0, 360.0),
                    class_id=0,
                )
            ]

        results = self.model.predict(  # type: ignore[union-attr]
            source=image_path_or_array,
            conf=self.confidence_threshold,
            device=self.device,
            verbose=False,
        )
        detections: List[Detection] = []
        for result in results:
            boxes = getattr(result, "boxes", None)
            if boxes is None:
                continue
            for box in boxes:
                conf = float(box.conf[0]) if hasattr(box, "conf") else 0.0
                if conf < self.confidence_threshold:
                    continue
                cls_id = int(box.cls[0]) if hasattr(box, "cls") else -1
                cls_name = str(self.model.names.get(cls_id, f"class_{cls_id}"))  # type: ignore[union-attr]
                coords = box.xyxy[0].tolist() if hasattr(box, "xyxy") else [0.0, 0.0, 0.0, 0.0]
                detections.append(
                    Detection(
                        class_name=cls_name,
                        confidence=conf,
                        bbox_xyxy=(float(coords[0]), float(coords[1]), float(coords[2]), float(coords[3])),
                        class_id=cls_id,
                    )
                )
        return detections

    def _normalize_class_name(self, class_name: str) -> str:
        normalized = class_name.lower().replace("[stub]", "").strip()
        return normalized

    def _category_for_class(self, class_name: str) -> ThreatCategory:
        normalized = self._normalize_class_name(class_name)
        if normalized in self.KINETIC_CLASSES:
            return ThreatCategory.KINETIC
        if normalized in self.SURVEILLANCE_CLASSES:
            return ThreatCategory.SURVEILLANCE
        return ThreatCategory.UNKNOWN

    def _level_for_class(self, class_name: str) -> ThreatLevel:
        normalized = self._normalize_class_name(class_name)
        return self.DEFAULT_CLASS_LEVELS.get(normalized, ThreatLevel.LOW)

    def detect_to_threats(self, image_path: str, location: Optional[Dict[str, Any]] = None) -> List[ThreatEvent]:
        """Convert detections into S3M threat events for Layer 01 consumption."""
        if not isinstance(image_path, str) or not image_path.strip():
            raise ValueError("image_path must be a non-empty string")
        if location is not None and not isinstance(location, dict):
            raise ValueError("location must be a dictionary or None")

        detections = self.detect(image_path)
        events: List[ThreatEvent] = []
        for detection in detections:
            level = self._level_for_class(detection.class_name)
            category = self._category_for_class(detection.class_name)
            bbox = list(detection.bbox_xyxy)
            events.append(
                ThreatEvent(
                    timestamp=datetime.now(timezone.utc),
                    source=ThreatSource.OBJECT_DETECTION,
                    level=level,
                    category=category,
                    title=f"Object detected: {detection.class_name}",
                    description=(
                        f"Visual sensor detected {detection.class_name} with confidence "
                        f"{detection.confidence:.2f}. Bounding box: {bbox}."
                    ),
                    raw_data={
                        "class_name": detection.class_name,
                        "confidence": detection.confidence,
                        "bbox_xyxy": bbox,
                        "class_id": detection.class_id,
                        "image_path": image_path,
                        "detector_mode": "stub" if self.stub_mode else "live",
                    },
                    confidence=max(0.0, min(1.0, float(detection.confidence))),
                    location=location,
                    recommended_action="Queue ISR verification and force-protection posture update.",
                )
            )
        return events

    def health_check(self) -> Dict[str, Any]:
        """Report detector readiness for tactical operations monitoring."""
        return {
            "status": "stub" if self.stub_mode else "ready",
            "model_path": self.model_path,
            "model_loaded": self.model is not None,
            "device": self.device,
            "confidence_threshold": self.confidence_threshold,
            "classes": self.available_classes,
        }
