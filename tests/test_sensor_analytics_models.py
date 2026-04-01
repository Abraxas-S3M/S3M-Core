"""Unit tests for Layer 09 sensor analytics dataclasses."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from services.sensor_analytics.models import (
    AISMessage,
    AISVessel,
    BorderAlert,
    BorderZone,
    MaritimePicture,
    SARDetection,
    SARImageMeta,
    VesselClassification,
)


def test_sar_image_meta_to_dict():
    meta = SARImageMeta(
        image_id="img1",
        source="sentinel-1",
        filepath="/tmp/a.tif",
        width=100,
        height=80,
        acquisition_time=datetime.now(timezone.utc),
        polarization="VV",
        resolution_meters=10.0,
        center_lat=25.0,
        center_lon=50.0,
        bounds={"north": 26.0, "south": 24.0, "east": 51.0, "west": 49.0},
        metadata={"orbit": "desc"},
    )
    payload = meta.to_dict()
    assert payload["image_id"] == "img1"
    assert payload["source"] == "sentinel-1"
    assert isinstance(payload["acquisition_time"], str)


def test_sar_detection_area_sq_meters():
    det = SARDetection(
        detection_id="d1",
        image_id="img1",
        bbox=(0, 0, 10, 5),
        geo_position=(25.0, 50.0),
        confidence=0.9,
        class_name="ship",
        estimated_length_meters=120.0,
        estimated_width_meters=20.0,
        heading_deg=None,
        speed_knots=None,
        model_used="stub",
        timestamp=datetime.now(timezone.utc),
    )
    assert det.area_sq_meters() == 2400.0
    assert det.to_dict()["model_not_loaded"] is True


def test_ais_message_underway():
    msg = AISMessage(
        mmsi="123456789",
        timestamp=datetime.now(timezone.utc),
        message_type=1,
        lat=25.0,
        lon=50.0,
        speed_knots=12.0,
        course_deg=90.0,
        heading_deg=90.0,
        vessel_name="V1",
        vessel_type=70,
        destination="DMM",
        nav_status=0,
        raw_nmea=None,
    )
    assert msg.is_underway()


def test_ais_vessel_is_dark():
    vessel = AISVessel(
        mmsi="123456789",
        vessel_name="V1",
        classification=VesselClassification.CARGO,
        flag_state="SAU",
        imo_number=None,
        length_meters=100.0,
        beam_meters=20.0,
        last_position=(25.0, 50.0),
        last_speed_knots=10.0,
        last_heading_deg=100.0,
        last_seen=datetime.now(timezone.utc) - timedelta(hours=2),
        positions_count=5,
        ais_active=True,
        risk_score=0.0,
        track=[],
    )
    assert vessel.is_dark()


def test_border_zone_contains_point():
    zone = BorderZone(
        zone_id="z1",
        name="Test Zone",
        zone_type="maritime_eez",
        polygon=[(0.0, 0.0), (0.0, 2.0), (2.0, 2.0), (2.0, 0.0)],
        threat_level="medium",
        active_sensors=["ais"],
    )
    assert zone.contains_point(1.0, 1.0) is True
    assert zone.contains_point(3.0, 3.0) is False


def test_border_alert_creation():
    alert = BorderAlert(
        alert_id="a1",
        zone_id="z1",
        timestamp=datetime.now(timezone.utc),
        alert_type="dark_vessel",
        severity="high",
        position=(25.0, 50.0),
        description="Unmatched SAR contact",
        vessel_id=None,
        confidence=0.8,
        evidence=[{"k": "v"}],
    )
    payload = alert.to_dict()
    assert payload["zone_id"] == "z1"
    assert payload["alert_type"] == "dark_vessel"


def test_maritime_picture_fields():
    picture = MaritimePicture(
        timestamp=datetime.now(timezone.utc),
        region="all",
        vessels=[{"mmsi": "1"}],
        sar_detections=[{"detection_id": "d1"}],
        border_alerts=[{"alert_id": "a1"}],
        zones=[{"zone_id": "z1"}],
        statistics={"total_vessels": 1, "dark_vessels": 1},
    )
    payload = picture.to_dict()
    assert payload["region"] == "all"
    assert payload["statistics"]["dark_vessels"] == 1
