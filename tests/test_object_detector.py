"""Tests for ObjectDetector."""

from __future__ import annotations

from src.threat_detection.models import ThreatCategory, ThreatLevel, ThreatSource
from src.threat_detection.object_detector import ObjectDetector


def test_stub_mode_when_model_missing() -> None:
    detector = ObjectDetector(model_path="/nonexistent/model.pt")
    assert detector.stub_mode is True


def test_class_mapping_to_threat_level() -> None:
    detector = ObjectDetector(model_path="/nonexistent/model.pt")
    assert detector._level_for_class("tank") == ThreatLevel.HIGH
    assert detector._level_for_class("aircraft") == ThreatLevel.CRITICAL


def test_detect_to_threats_returns_events() -> None:
    detector = ObjectDetector(model_path="/nonexistent/model.pt")
    events = detector.detect_to_threats(image_path="dummy.jpg", location={"sector": "A1"})
    assert len(events) >= 1
    event = events[0]
    assert event.source == ThreatSource.OBJECT_DETECTION
    assert event.category in {ThreatCategory.KINETIC, ThreatCategory.SURVEILLANCE, ThreatCategory.UNKNOWN}


def test_health_check() -> None:
    detector = ObjectDetector(model_path="/nonexistent/model.pt")
    health = detector.health_check()
    assert "status" in health
    assert "device" in health
