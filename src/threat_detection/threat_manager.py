"""Central threat ingestion manager for S3M Layer 02."""

from __future__ import annotations

import json
import os
import time
from collections import deque
from datetime import datetime, timezone
from typing import Dict, List, Optional

from src.threat_detection.anomaly_detector import AnomalyDetector
from src.threat_detection.models import DetectionResult, ThreatCategory, ThreatEvent, ThreatLevel, ThreatSource
from src.threat_detection.object_detector import ObjectDetector
from src.threat_detection.suricata_adapter import SuricataAdapter
from src.threat_detection.threat_classifier import ThreatClassifier
from src.threat_detection.wazuh_adapter import WazuhAdapter


class ThreatManager:
    """Coordinate all tactical detection sources into one event stream."""

    def __init__(self, max_entries: int = 10_000, object_model_path: Optional[str] = None) -> None:
        if not isinstance(max_entries, int) or max_entries <= 0:
            raise ValueError("max_entries must be a positive integer")
        self.max_entries = max_entries
        self.suricata = SuricataAdapter()
        self.wazuh = WazuhAdapter()
        self.anomaly = AnomalyDetector()
        self.classifier = ThreatClassifier()
        self.object_detector: Optional[ObjectDetector] = None
        if object_model_path:
            self.object_detector = ObjectDetector(model_path=object_model_path)
        self._threat_log: deque[ThreatEvent] = deque(maxlen=self.max_entries)

    def _build_result(self, source: ThreatSource, start_time: float, events: List[ThreatEvent]) -> DetectionResult:
        by_level: Dict[str, int] = {}
        for event in events:
            by_level[event.level.name] = by_level.get(event.level.name, 0) + 1
            self._threat_log.append(event)
        return DetectionResult(
            source=source,
            processing_time_ms=(time.time() - start_time) * 1000.0,
            total_events=len(events),
            events_by_level=by_level,
            events=events,
        )

    def ingest_suricata_log(self, filepath: str) -> DetectionResult:
        start = time.time()
        events = self.suricata.parse_eve_log(filepath)
        return self._build_result(ThreatSource.NETWORK_IDS, start, events)

    def ingest_wazuh_alerts(self, filepath: str) -> DetectionResult:
        start = time.time()
        events = self.wazuh.parse_alerts_file(filepath)
        return self._build_result(ThreatSource.ENDPOINT_SIEM, start, events)

    def ingest_image(self, image_path: str, location: Optional[Dict[str, object]] = None) -> DetectionResult:
        start = time.time()
        if self.object_detector is None:
            self.object_detector = ObjectDetector(model_path="models/yolov8n-military.pt")
        events = self.object_detector.detect_to_threats(image_path=image_path, location=location)
        return self._build_result(ThreatSource.OBJECT_DETECTION, start, events)

    def ingest_telemetry(
        self,
        data: List[List[float]],
        feature_names: Optional[List[str]] = None,
    ) -> DetectionResult:
        start = time.time()
        events = self.anomaly.detect(data, feature_names=feature_names)
        return self._build_result(ThreatSource.ANOMALY_DETECTION, start, events)

    def ingest_manual(
        self,
        title: str,
        description: str,
        level: str,
        category: str,
    ) -> ThreatEvent:
        event = ThreatEvent(
            source=ThreatSource.MANUAL,
            level=ThreatLevel.from_value(level),
            category=ThreatCategory.from_value(category),
            title=title,
            description=description,
            confidence=1.0,
            raw_data={"origin": "manual_operator_input"},
            recommended_action="Escalate to tactical command post for confirmation and response assignment.",
        )
        self._threat_log.append(event)
        return event

    def get_threats(
        self,
        level: Optional[str] = None,
        source: Optional[str] = None,
        category: Optional[str] = None,
        limit: int = 50,
    ) -> List[ThreatEvent]:
        if not isinstance(limit, int) or limit <= 0:
            raise ValueError("limit must be a positive integer")
        level_filter = ThreatLevel.from_value(level) if level else None
        source_filter = ThreatSource.from_value(source) if source else None
        category_filter = ThreatCategory.from_value(category) if category else None
        results: List[ThreatEvent] = []
        for event in reversed(self._threat_log):
            if level_filter and event.level != level_filter:
                continue
            if source_filter and event.source != source_filter:
                continue
            if category_filter and event.category != category_filter:
                continue
            results.append(event)
            if len(results) >= limit:
                break
        return results

    def get_stats(self) -> Dict[str, object]:
        by_level: Dict[str, int] = {}
        by_source: Dict[str, int] = {}
        by_category: Dict[str, int] = {}
        for event in self._threat_log:
            by_level[event.level.name] = by_level.get(event.level.name, 0) + 1
            by_source[event.source.value] = by_source.get(event.source.value, 0) + 1
            by_category[event.category.value] = by_category.get(event.category.value, 0) + 1
        last_event_timestamp = self._threat_log[-1].timestamp.isoformat() if self._threat_log else None
        return {
            "total_events": len(self._threat_log),
            "events_by_level": by_level,
            "events_by_source": by_source,
            "events_by_category": by_category,
            "last_event_timestamp": last_event_timestamp,
            "max_entries": self.max_entries,
        }

    def assess_threat(self, event_id: str) -> ThreatEvent:
        if not isinstance(event_id, str) or not event_id.strip():
            raise ValueError("event_id must be a non-empty string")
        for event in self._threat_log:
            if event.event_id == event_id:
                return self.classifier.classify(event)
        raise ValueError(f"Threat event not found: {event_id}")

    def generate_sitrep(self) -> str:
        recent_priority = [
            event
            for event in self.get_threats(limit=200)
            if event.level in (ThreatLevel.HIGH, ThreatLevel.CRITICAL)
        ]
        if not recent_priority:
            return "SITREP: No HIGH/CRITICAL threats in current tactical window."
        return self.classifier.generate_sitrep(recent_priority)

    def export_log(self, filepath: str) -> None:
        if not isinstance(filepath, str) or not filepath.strip():
            raise ValueError("filepath must be a non-empty string")
        export_dir = os.path.dirname(filepath)
        if export_dir:
            os.makedirs(export_dir, exist_ok=True)
        with open(filepath, "w", encoding="utf-8") as handle:
            payload = {
                "exported_at": datetime.now(timezone.utc).isoformat(),
                "total_events": len(self._threat_log),
                "events": [event.to_dict() for event in self._threat_log],
            }
            json.dump(payload, handle, indent=2)

    def clear_log(self) -> None:
        self._threat_log.clear()
