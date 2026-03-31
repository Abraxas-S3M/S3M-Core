"""Unit tests for anomaly detector pipeline."""

from __future__ import annotations

from src.threat_detection.anomaly_detector import AnomalyDetector
from src.threat_detection.models import ThreatCategory, ThreatSource


def test_fit_on_normal_data():
    detector = AnomalyDetector(contamination=0.2, n_estimators=32)
    baseline = [[1.0, 1.1], [1.0, 0.9], [0.95, 1.0], [1.1, 1.0]]
    detector.fit(baseline)
    health = detector.health_check()
    assert health["status"] == "ready"
    assert health["training_samples"] == 4


def test_detect_anomalies_with_outliers_zscore_path():
    detector = AnomalyDetector(contamination=0.2, n_estimators=32)
    detector._backend = "zscore"
    detector._model = None
    baseline = [[1.0, 1.0], [1.1, 0.9], [0.9, 1.1], [1.0, 1.0], [1.05, 0.95]]
    detector.fit(baseline)
    anomalies = detector.detect([[1.0, 1.0], [20.0, 25.0]], feature_names=["network_latency", "packet_drop"])
    assert len(anomalies) >= 1
    assert anomalies[0].source == ThreatSource.ANOMALY_DETECTION
    assert anomalies[0].category == ThreatCategory.CYBER


def test_threat_event_output_shape():
    detector = AnomalyDetector(contamination=0.2, n_estimators=32)
    detector._backend = "zscore"
    detector._model = None
    detector.fit([[1.0, 1.0], [1.1, 1.0], [0.9, 1.0], [1.0, 1.1], [1.0, 0.9]])
    events = detector.detect([[7.0, 8.0]], feature_names=["rf_power", "rf_noise"])
    assert len(events) == 1
    event = events[0]
    assert event.raw_data["backend"] == "zscore"
    assert event.category == ThreatCategory.ELECTRONIC_WARFARE


def test_fallback_when_sklearn_unavailable():
    detector = AnomalyDetector()
    detector._backend = "zscore"
    detector._model = None
    detector.fit([[1.0, 2.0], [1.1, 1.9], [0.9, 2.1]])
    events = detector.detect([[10.0, -5.0]], feature_names=["packet_rate", "latency"])
    assert len(events) == 1
