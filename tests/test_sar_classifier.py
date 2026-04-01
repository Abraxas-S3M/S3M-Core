"""Unit tests for SAR vessel classifier heuristics."""

from __future__ import annotations

from datetime import datetime, timezone

from services.sensor_analytics.models import SARDetection
from services.sensor_analytics.sar.classifier import SARShipClassifier


def _det(length: float, width: float) -> SARDetection:
    return SARDetection(
        detection_id="d1",
        image_id="img1",
        bbox=(0.0, 0.0, 10.0, 10.0),
        geo_position=(25.0, 50.0),
        confidence=0.8,
        class_name="ship",
        estimated_length_meters=length,
        estimated_width_meters=width,
        heading_deg=None,
        speed_knots=None,
        model_used="stub",
        timestamp=datetime.now(timezone.utc),
    )


def test_classify_length_300_returns_large_vessel():
    cls = SARShipClassifier().classify(_det(300.0, 35.0))
    assert cls.value in {"CARGO", "TANKER"}


def test_classify_length_30_ratio_25_returns_fishing():
    cls = SARShipClassifier().classify(_det(30.0, 12.0))
    assert cls.value == "FISHING"


def test_classify_length_120_ratio_4_returns_military_surface():
    cls = SARShipClassifier().classify(_det(120.0, 30.0))
    assert cls.value == "MILITARY_SURFACE"


def test_enrich_from_ais_uses_ais_type_when_available():
    classifier = SARShipClassifier()
    det = _det(70.0, 12.0)
    enriched = classifier.enrich_from_ais(det, ais_vessel={"classification": "TANKER", "mmsi": "123"})
    assert enriched["classification"] == "TANKER"
