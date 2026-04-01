"""Unit tests for border surveillance and zone management."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from services.sensor_analytics.ais.tracker import AISTracker
from services.sensor_analytics.border.surveillance_engine import BorderSurveillanceEngine
from services.sensor_analytics.border.zone_manager import ZoneManager
from services.sensor_analytics.models import AISVessel, BorderAlert, VesselClassification


def test_zone_manager_loads_zones() -> None:
    manager = ZoneManager("configs/sensor-analytics/zones.yaml")
    zones = manager.load_zones()
    assert len(zones) >= 6


def test_zone_manager_check_position() -> None:
    manager = ZoneManager("configs/sensor-analytics/zones.yaml")
    zones = manager.check_position(27.0, 35.0)
    assert len(zones) >= 1


def test_border_surveillance_scan_zone_returns_alerts() -> None:
    tracker = AISTracker()
    engine = BorderSurveillanceEngine(ais_tracker=tracker, zone_manager=ZoneManager("configs/sensor-analytics/zones.yaml"))
    now = datetime.now(timezone.utc) - timedelta(hours=2)
    vessel = AISVessel(
        mmsi="444000444",
        vessel_name="Dark Candidate",
        classification=VesselClassification.UNKNOWN,
        flag_state="UNKNOWN",
        imo_number=None,
        length_meters=70.0,
        beam_meters=10.0,
        last_position=(27.0, 35.0),
        last_speed_knots=0.5,
        last_heading_deg=5.0,
        last_seen=now,
        positions_count=5,
        ais_active=True,
        risk_score=0.0,
        track=[{"timestamp": now.isoformat(), "lat": 27.0, "lon": 35.0, "speed_knots": 0.5, "heading_deg": 5.0}],
    )
    tracker.vessels[vessel.mmsi] = vessel
    zone = engine.zone_manager.get_zones()[0]
    alerts = engine.scan_zone(zone)
    assert isinstance(alerts, list)


def test_feed_to_threat_detection_creates_events() -> None:
    engine = BorderSurveillanceEngine(zone_manager=ZoneManager("configs/sensor-analytics/zones.yaml"))
    alert = BorderAlert(
        alert_id="a1",
        zone_id="ZONE-RS-NORTH",
        timestamp=datetime.now(timezone.utc),
        alert_type="dark_vessel",
        severity="high",
        position=(27.0, 35.0),
        description="Dark vessel",
        vessel_id=None,
        confidence=0.9,
        evidence=[],
    )
    events = engine.feed_to_threat_detection([alert])
    assert len(events) == 1
