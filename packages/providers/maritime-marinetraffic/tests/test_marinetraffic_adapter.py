from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))))

from integration_sdk.base.provider_adapter import OperatingMode
from packages.providers.maritime_marinetraffic.adapter import MarineTrafficAdapter
from packages.providers.maritime_marinetraffic.config import MONITORING_ZONES


def test_manifest_correct() -> None:
    m = MarineTrafficAdapter(mode=OperatingMode.AIRGAPPED).get_manifest()
    assert m.provider_id == "maritime-marinetraffic"
    assert m.category.value == "maritime"
    assert m.tier.value == "freemium"
    assert m.auth_type == "api_key"


def test_speed_conversion() -> None:
    adapter = MarineTrafficAdapter(mode=OperatingMode.AIRGAPPED)
    vessel = adapter.fetch_zone_vessels("persian_gulf")["vessels"][0]
    normalized = adapter.normalizer.normalize_vessel(vessel)
    assert normalized.speed_knots == 12.5


def test_draught_conversion() -> None:
    adapter = MarineTrafficAdapter(mode=OperatingMode.AIRGAPPED)
    vessel = adapter.fetch_zone_vessels("persian_gulf")["vessels"][0]
    normalized = adapter.normalizer.normalize_vessel(vessel)
    assert normalized.draught_m == 20.0


def test_ship_type_mapping() -> None:
    n = MarineTrafficAdapter(mode=OperatingMode.AIRGAPPED).normalizer
    assert n._ship_type_name(7) == "Cargo"
    assert n._ship_type_name(8) == "Tanker"


def test_nav_status_mapping() -> None:
    n = MarineTrafficAdapter(mode=OperatingMode.AIRGAPPED).normalizer
    assert n._nav_status_name(0) == "underway using engine"
    assert n._nav_status_name(5) == "moored"


def test_normalize_vessel_all_fields() -> None:
    adapter = MarineTrafficAdapter(mode=OperatingMode.AIRGAPPED)
    vessel = adapter.fetch_zone_vessels("persian_gulf")["vessels"][0]
    track = adapter.normalizer.normalize_vessel(vessel)
    assert track.mmsi and track.vessel_name and track.vessel_type
    assert track.geo_point is not None
    assert track.timestamp is not None
    assert track.provenance.confidence == 0.95


def test_normalize_batch_count() -> None:
    adapter = MarineTrafficAdapter(mode=OperatingMode.AIRGAPPED)
    payload = adapter.fetch_zone_vessels("persian_gulf")
    tracks = adapter.normalizer.normalize_batch(payload["vessels"])
    assert len(tracks) == 25


def test_monitoring_zones_defined() -> None:
    assert set(MONITORING_ZONES.keys()) == {
        "persian_gulf", "red_sea_south", "strait_of_hormuz", "bab_el_mandeb", "jubail_coast", "gulf_of_aden"
    }
    assert MONITORING_ZONES["strait_of_hormuz"] == {"minlat": 25.5, "maxlat": 26.5, "minlon": 56.0, "maxlon": 57.0}


def test_ais_gap_detection() -> None:
    adapter = MarineTrafficAdapter(mode=OperatingMode.AIRGAPPED)
    events = adapter.fetch_vessel_events("636092400")["events"] + adapter.fetch_vessel_events("563001201")["events"]
    gaps = adapter.normalizer.detect_ais_gaps(events)
    assert len(gaps) >= 2
    assert any(abs(g["duration_hours"] - 18.0) < 0.01 and g["dark_vessel_flag"] for g in gaps)


def test_fetch_all_zones_deduplicates() -> None:
    adapter = MarineTrafficAdapter(mode=OperatingMode.AIRGAPPED)
    merged = adapter.fetch_all_saudi_zones(60)
    sum_counts = sum(v["count"] for v in merged["by_zone"].values())
    assert merged["total_vessels"] < sum_counts


def test_confidence_high() -> None:
    adapter = MarineTrafficAdapter(mode=OperatingMode.AIRGAPPED)
    vessel = adapter.fetch_zone_vessels("persian_gulf")["vessels"][0]
    track = adapter.normalizer.normalize_vessel(vessel)
    assert track.provenance.confidence == 0.95


def test_fetch_airgapped() -> None:
    adapter = MarineTrafficAdapter(mode=OperatingMode.AIRGAPPED)
    data = adapter.fetch_zone_vessels("persian_gulf")
    assert data["count"] == 25


def test_health_check_structure() -> None:
    health = MarineTrafficAdapter(mode=OperatingMode.AIRGAPPED).health_check()
    assert {"status", "latency_ms", "error_count", "detail"}.issubset(set(health.keys()))
