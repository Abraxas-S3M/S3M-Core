#!/usr/bin/env python3
"""Unit tests for AIS tracking and SAR matching."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from services.sensor_analytics.ais.tracker import AISTracker
from services.sensor_analytics.models import AISMessage, BorderZone, SARDetection


def _msg(mmsi: str, lat: float, lon: float, speed: float = 12.0, heading: float = 90.0) -> AISMessage:
    return AISMessage(
        mmsi=mmsi,
        timestamp=datetime.now(timezone.utc),
        message_type=1,
        lat=lat,
        lon=lon,
        speed_knots=speed,
        course_deg=heading,
        heading_deg=heading,
        vessel_name="Test",
        vessel_type=70,
        destination="DMM",
        nav_status=0,
    )


def test_update_creates_new_vessel_for_unknown_mmsi():
    tracker = AISTracker()
    tracker.update(_msg("123456789", 26.0, 50.0))
    assert tracker.get_vessel("123456789") is not None


def test_update_appends_track_history():
    tracker = AISTracker()
    tracker.update(_msg("123456789", 26.0, 50.0))
    tracker.update(_msg("123456789", 26.1, 50.1))
    vessel = tracker.get_vessel("123456789")
    assert vessel is not None
    assert len(vessel.track) == 2


def test_get_dark_vessels_detects_stale_vessel():
    tracker = AISTracker()
    tracker.update(_msg("123456789", 26.0, 50.0))
    vessel = tracker.get_vessel("123456789")
    assert vessel is not None
    vessel.last_seen = datetime.now(timezone.utc) - timedelta(hours=2)
    dark = tracker.get_dark_vessels()
    assert any(v.mmsi == "123456789" for v in dark)


def test_get_vessels_in_zone_returns_inside_only():
    tracker = AISTracker()
    tracker.update(_msg("111111111", 26.0, 50.0))
    tracker.update(_msg("222222222", 30.0, 60.0))
    zone = BorderZone(
        zone_id="Z1",
        name="Test zone",
        zone_type="maritime_eez",
        polygon=[(25.0, 49.0), (27.0, 49.0), (27.0, 51.0), (25.0, 51.0)],
        threat_level="medium",
        active_sensors=["ais"],
    )
    vessels = tracker.get_vessels_in_zone(zone)
    ids = {v.mmsi for v in vessels}
    assert "111111111" in ids
    assert "222222222" not in ids


def test_match_sar_detection_within_radius():
    tracker = AISTracker()
    tracker.update(_msg("123456789", 26.0, 50.0))
    det = SARDetection(
        detection_id="d1",
        image_id="img",
        bbox=(0, 0, 10, 10),
        geo_position=(26.02, 50.01),
        confidence=0.8,
        class_name="ship",
        estimated_length_meters=100.0,
        estimated_width_meters=20.0,
        heading_deg=None,
        speed_knots=None,
        model_used="stub",
        timestamp=datetime.now(timezone.utc),
    )
    match = tracker.match_sar_detection(det, radius_km=5.0)
    assert match is not None
    assert match.mmsi == "123456789"


def test_compute_risk_score_increases_for_dark_vessel():
    tracker = AISTracker()
    tracker.update(_msg("123456789", 26.0, 50.0))
    vessel = tracker.get_vessel("123456789")
    assert vessel is not None
    base = tracker.compute_risk_score(vessel)
    vessel.last_seen = datetime.now(timezone.utc) - timedelta(hours=2)
    vessel.ais_active = False
    dark_score = tracker.compute_risk_score(vessel)
    assert dark_score > base
