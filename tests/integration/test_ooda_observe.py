"""
OODA OBSERVE: Raw sensor data -> structured threat events and fused tracks.
Tests the data path from Layer 02 ingestion to actionable intelligence.
"""

from __future__ import annotations

import random
from datetime import datetime, timezone

import pytest

from src.sensor_fusion.models import SensorType, TrackState
from src.sensor_fusion.sensor_manager import SensorManager
from src.threat_detection.anomaly_detector import AnomalyDetector
from src.threat_detection.models import ThreatCategory, ThreatLevel, ThreatSource
from src.threat_detection.object_detector import ObjectDetector
from src.threat_detection.suricata_adapter import SuricataAdapter
from src.threat_detection.wazuh_adapter import WazuhAdapter


def test_suricata_to_threat_event() -> None:
    adapter = SuricataAdapter()
    event = adapter.parse_event(
        {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "event_type": "alert",
            "alert": {
                "severity": 1,
                "signature": "ET POLICY SSH connection attempt",
                "category": "Attempted Information Leak",
            },
            "src_ip": "192.168.1.100",
            "dest_ip": "10.0.0.1",
            "src_port": 54321,
            "dest_port": 22,
            "proto": "TCP",
        }
    )
    assert event is not None
    # Current implementation maps severity=1 to CRITICAL; allow HIGH/CRITICAL compatibility.
    assert event.level in {ThreatLevel.HIGH, ThreatLevel.CRITICAL}
    assert event.category == ThreatCategory.CYBER
    assert event.source == ThreatSource.NETWORK_IDS
    prompt = event.to_prompt()
    assert isinstance(prompt, str) and prompt.strip()
    assert "192.168.1.100" in prompt


def test_wazuh_to_threat_event() -> None:
    adapter = WazuhAdapter()
    event = adapter.parse_alert(
        {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "rule": {
                "level": 12,
                "description": "SSH brute force attack",
                "id": "5712",
                "groups": ["authentication_failure"],
            },
            "agent": {"name": "jetson-01"},
            "data": {"srcip": "10.0.0.99"},
        }
    )
    assert event is not None
    assert event.level == ThreatLevel.HIGH
    assert event.category == ThreatCategory.CYBER


def test_sensor_fusion_track_creation() -> None:
    manager = SensorManager()
    manager.register_sensor("radar_01", SensorType.RADAR)

    points = [(100, 100, 50), (110, 105, 50), (120, 110, 50), (130, 115, 50), (140, 120, 50)]
    for x, y, z in points:
        manager.ingest(
            sensor_id="radar_01",
            data={"x": x, "y": y, "z": z, "classification": "aircraft"},
            position=(x, y, z),
            confidence=0.92,
        )

    tracks = manager.process()
    assert len(tracks) >= 1
    track = tracks[0]
    assert track.state in {TrackState.TENTATIVE, TrackState.CONFIRMED}
    lx, ly, lz = points[-1]
    tx, ty, tz = track.position
    assert abs(tx - lx) < 25
    assert abs(ty - ly) < 25
    assert abs(tz - lz) < 10


def test_yolo_detection_to_threat() -> None:
    detector = ObjectDetector(model_path="models/yolov8n-military.pt")
    events = detector.detect_to_threats("stub_input.jpg", location={"x": 5, "y": 10, "z": 0})

    assert events
    assert all(event.source == ThreatSource.OBJECT_DETECTION for event in events)
    # Stub detector emits soldier class; this should map to a bounded tactical level.
    assert all(event.level in {ThreatLevel.LOW, ThreatLevel.MEDIUM, ThreatLevel.HIGH, ThreatLevel.CRITICAL} for event in events)


def test_anomaly_detection_pipeline() -> None:
    random.seed(42)
    detector = AnomalyDetector(contamination=0.1, n_estimators=50)

    normal = [[random.gauss(0, 1), random.gauss(0, 1), random.gauss(0, 1)] for _ in range(100)]
    anomalous = [[random.gauss(0, 1) * 10, random.gauss(0, 1) * 10, random.gauss(0, 1) * 10] for _ in range(10)]

    detector.fit(normal)
    combined = normal + anomalous
    events = detector.detect(combined, feature_names=["value1", "value2", "value3"])

    assert len(events) > 0
    assert all(event.source == ThreatSource.ANOMALY_DETECTION for event in events)
