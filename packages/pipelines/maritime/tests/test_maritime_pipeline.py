from __future__ import annotations

import os
import sys
from datetime import datetime, timedelta, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))))

from integration_sdk.base.provider_adapter import OperatingMode
from packages.pipelines.maritime.maritime_pipeline import MaritimeFusionPipeline
from packages.schemas.common.base import GeoPoint, Provenance
from packages.schemas.maritime.models import NormalizedVesselTrack


def _track(mmsi: str, ts_offset_min: int, lat: float, lon: float) -> NormalizedVesselTrack:
    return NormalizedVesselTrack(
        mmsi=mmsi,
        vessel_name=f"V-{mmsi}",
        vessel_type="Tanker",
        flag_state="SA",
        speed_knots=12.0,
        course_deg=220.0,
        heading_deg=221.0,
        nav_status="underway using engine",
        timestamp=datetime.now(timezone.utc) - timedelta(minutes=ts_offset_min),
        geo_point=GeoPoint(lat=lat, lon=lon),
        provenance=Provenance(
            provider_id="test",
            provider_name="test",
            fetched_at=datetime.now(timezone.utc),
            raw_id=mmsi,
            confidence=0.9,
            classification="UNCLASSIFIED",
        ),
        tags=["zone:bab_el_mandeb"],
    )


def test_ingest_all_merges_by_mmsi() -> None:
    p = MaritimeFusionPipeline(mode=OperatingMode.AIRGAPPED)
    res = p.ingest_all_zones(60)
    assert res["total_vessels"] > 0
    assert res["dedup_count"] > 0


def test_merge_takes_most_recent_position() -> None:
    p = MaritimeFusionPipeline(mode=OperatingMode.AIRGAPPED)
    a = _track("111", 20, 20.0, 20.0)
    b = _track("111", 1, 21.0, 21.0)
    merged = p._merge_tracks([a, b])
    assert len(merged) == 1
    assert merged[0].geo_point.lat == 21.0


def test_satellite_confirmed_tag() -> None:
    p = MaritimeFusionPipeline(mode=OperatingMode.AIRGAPPED)
    res = p.ingest_all_zones(60)
    assert res["satellite_confirmed"] >= 1


def test_enrich_with_risk_adds_score() -> None:
    p = MaritimeFusionPipeline(mode=OperatingMode.AIRGAPPED)
    p.ingest_all_zones(60)
    enriched = p.enrich_with_risk(p._last_vessels)
    assert any(hasattr(v, "risk_score") for v in enriched)


def test_dark_vessel_detection_cross_provider() -> None:
    p = MaritimeFusionPipeline(mode=OperatingMode.AIRGAPPED)
    dark = p.detect_dark_vessels()
    assert len(dark) >= 1
    assert any(d["dark_source"] in {"satellite_only", "ais_gap+satellite", "windward_dark_activity", "ais_gap_event"} for d in dark)


def test_feed_to_phase15_writes_csv() -> None:
    p = MaritimeFusionPipeline(mode=OperatingMode.AIRGAPPED)
    p.ingest_all_zones(60)
    path = p.feed_to_phase15(p._last_vessels)
    assert os.path.exists(path)


def test_feed_dark_to_border_surveillance() -> None:
    p = MaritimeFusionPipeline(mode=OperatingMode.AIRGAPPED)
    events = p.feed_dark_vessels_to_border_surveillance([
        {"mmsi": "123", "dark_source": "satellite_only", "last_known_position": {"lat": 12.7, "lon": 43.3}}
    ])
    assert len(events) == 1


def test_chokepoint_status_all_three() -> None:
    p = MaritimeFusionPipeline(mode=OperatingMode.AIRGAPPED)
    p.ingest_all_zones(60)
    p.detect_dark_vessels()
    status = p.get_chokepoint_status()
    assert set(status.keys()) == {"strait_of_hormuz", "bab_el_mandeb", "gulf_of_aden"}


def test_chokepoint_tanker_count() -> None:
    p = MaritimeFusionPipeline(mode=OperatingMode.AIRGAPPED)
    p.ingest_all_zones(60)
    status = p.get_chokepoint_status()
    assert status["strait_of_hormuz"]["tankers"] >= 0


def test_health_check_all_providers() -> None:
    p = MaritimeFusionPipeline(mode=OperatingMode.AIRGAPPED)
    health = p.health_check()
    assert set(health["providers"].keys()) == {
        "maritime-marinetraffic", "maritime-vesselfinder", "maritime-spire", "maritime-windward"
    }
