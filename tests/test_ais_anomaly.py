from __future__ import annotations

from datetime import datetime, timedelta, timezone

from services.sensor_analytics.ais import AISAnomalyDetector
from services.sensor_analytics.models import AISVessel, VesselClassification


def _make_vessel() -> AISVessel:
    now = datetime.now(timezone.utc)
    return AISVessel(
        mmsi="111000111",
        vessel_name="TEST",
        classification=VesselClassification.CARGO,
        flag_state="SA",
        imo_number=None,
        length_meters=120.0,
        beam_meters=20.0,
        last_position=(25.0, 50.0),
        last_speed_knots=12.0,
        last_heading_deg=90.0,
        last_seen=now,
        positions_count=2,
        ais_active=True,
        risk_score=0.0,
        track=[],
    )


def test_detect_anomalies_finds_ais_gap():
    detector = AISAnomalyDetector()
    vessel = _make_vessel()
    vessel.last_seen = datetime.now(timezone.utc) - timedelta(hours=2)
    vessel.track = [
        {"timestamp": (datetime.now(timezone.utc) - timedelta(hours=2)).isoformat(), "lat": 25.0, "lon": 50.0, "speed_knots": 10.0, "heading_deg": 90.0},
        {"timestamp": (datetime.now(timezone.utc) - timedelta(hours=1, minutes=30)).isoformat(), "lat": 25.1, "lon": 50.1, "speed_knots": 10.0, "heading_deg": 90.0},
    ]
    anomalies = detector.detect_anomalies(vessel)
    assert any(a["anomaly_type"] == "ais_gap" for a in anomalies)


def test_detect_anomalies_finds_speed_anomaly():
    detector = AISAnomalyDetector()
    vessel = _make_vessel()
    now = datetime.now(timezone.utc)
    vessel.track = [
        {"timestamp": (now - timedelta(minutes=6)).isoformat(), "lat": 25.0, "lon": 50.0, "speed_knots": 10.0, "heading_deg": 90.0},
        {"timestamp": now.isoformat(), "lat": 25.05, "lon": 50.03, "speed_knots": 20.0, "heading_deg": 92.0},
    ]
    anomalies = detector.detect_anomalies(vessel)
    assert any(a["anomaly_type"] == "speed_anomaly" for a in anomalies)


def test_detect_anomalies_finds_position_spoofing():
    detector = AISAnomalyDetector()
    vessel = _make_vessel()
    now = datetime.now(timezone.utc)
    vessel.track = [
        {"timestamp": (now - timedelta(minutes=2)).isoformat(), "lat": 25.0, "lon": 50.0, "speed_knots": 12.0, "heading_deg": 90.0},
        {"timestamp": now.isoformat(), "lat": 26.5, "lon": 51.5, "speed_knots": 12.0, "heading_deg": 90.0},
    ]
    anomalies = detector.detect_anomalies(vessel)
    assert any(a["anomaly_type"] == "position_spoofing" for a in anomalies)


def test_to_border_alerts():
    detector = AISAnomalyDetector()
    vessel = _make_vessel()
    anomalies = [
        {
            "anomaly_type": "ais_gap",
            "severity": "high",
            "detail": "gap",
            "timestamp": datetime.now(timezone.utc),
            "position": (25.0, 50.0),
        }
    ]
    alerts = detector.to_border_alerts(anomalies, vessel)
    assert len(alerts) == 1
    assert alerts[0].alert_type == "ais_gap"
