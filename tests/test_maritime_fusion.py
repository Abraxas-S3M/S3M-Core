"""Tests for Layer 09 maritime fusion."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from services.sensor_analytics.fusion_engine import MaritimeFusionEngine
from services.sensor_analytics.models import AISVessel, SARDetection, VesselClassification


def _sample_detection(lat: float, lon: float, detection_id: str = "det-1") -> SARDetection:
    return SARDetection(
        detection_id=detection_id,
        image_id="img-1",
        bbox=(0.0, 0.0, 10.0, 10.0),
        geo_position=(lat, lon),
        confidence=0.9,
        class_name="ship",
        estimated_length_meters=120.0,
        estimated_width_meters=20.0,
        heading_deg=45.0,
        speed_knots=12.0,
        model_used="stub",
        timestamp=datetime.now(timezone.utc),
    )


def test_fuse_with_sar_and_ais_produces_picture(tmp_path):
    csv_path = tmp_path / "ais.csv"
    csv_path.write_text(
        "MMSI,timestamp,lat,lon,speed,course,heading,vessel_name,vessel_type,destination,nav_status\n"
        "123456789,2026-01-01T00:00:00Z,25.0000,50.0000,10,90,90,ALPHA,70,PORT,0\n",
        encoding="utf-8",
    )
    engine = MaritimeFusionEngine()
    det = _sample_detection(25.0001, 50.0001)
    picture = engine.fuse(sar_detections=[det], ais_data_path=str(csv_path))
    assert picture.region == "all"
    assert isinstance(picture.vessels, list)


def test_unmatched_sar_detection_flagged_dark():
    engine = MaritimeFusionEngine()
    det = _sample_detection(10.0, 10.0, detection_id="dark-det")
    picture = engine.fuse(sar_detections=[det])
    assert len(picture.sar_detections) >= 1


def test_matched_sar_ais_enriched_vessel_entry():
    engine = MaritimeFusionEngine()
    vessel = AISVessel(
        mmsi="111222333",
        vessel_name="MATCHED",
        classification=VesselClassification.CARGO,
        flag_state="SA",
        imo_number=None,
        length_meters=100.0,
        beam_meters=20.0,
        last_position=(25.0, 50.0),
        last_speed_knots=10.0,
        last_heading_deg=90.0,
        last_seen=datetime.now(timezone.utc),
        positions_count=1,
        ais_active=True,
        risk_score=0.0,
        track=[{"timestamp": datetime.now(timezone.utc).isoformat(), "lat": 25.0, "lon": 50.0, "speed_knots": 10.0, "heading_deg": 90.0}],
    )
    engine.ais_tracker.vessels[vessel.mmsi] = vessel
    det = _sample_detection(25.0001, 50.0001, detection_id="match-det")
    picture = engine.fuse(sar_detections=[det])
    assert any(v["mmsi"] == "111222333" for v in picture.vessels)


def test_get_dark_vessels_returns_unmatched_and_ais_gap():
    engine = MaritimeFusionEngine()
    stale = AISVessel(
        mmsi="999888777",
        vessel_name="STALE",
        classification=VesselClassification.UNKNOWN,
        flag_state="UNKNOWN",
        imo_number=None,
        length_meters=0.0,
        beam_meters=0.0,
        last_position=(26.0, 50.0),
        last_speed_knots=0.0,
        last_heading_deg=0.0,
        last_seen=datetime.now(timezone.utc) - timedelta(hours=2),
        positions_count=2,
        ais_active=True,
        risk_score=0.0,
        track=[],
    )
    engine.ais_tracker.vessels[stale.mmsi] = stale
    det = _sample_detection(10.0, 10.0, detection_id="dark-2")
    engine.fuse(sar_detections=[det])
    dark = engine.get_dark_vessels()
    assert len(dark) >= 2


def test_process_sar_image_end_to_end(tmp_path):
    import numpy as np
    from PIL import Image

    image_path = tmp_path / "sar.png"
    arr = np.zeros((128, 128), dtype=np.uint8)
    arr[40:48, 60:70] = 255
    Image.fromarray(arr).save(image_path)

    engine = MaritimeFusionEngine()
    result = engine.process_sar_image(str(image_path))
    assert "detections" in result
    assert "picture" in result
