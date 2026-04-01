from __future__ import annotations

import json
import os
import sys
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))))

from packages.providers.gis_mapbox.adapter import MapboxAdapter
from packages.providers.gis_mapbox.config import MapboxConfig
from packages.providers.gis_mapbox.normalizer import MapboxNormalizer


FIXTURE_DIR = Path(__file__).resolve().parents[1] / "fixtures"


def test_manifest_correct() -> None:
    manifest = MapboxAdapter(mode="airgapped").get_manifest()
    assert manifest.provider_id == "gis-mapbox"
    assert manifest.category == "MAPPING_TERRAIN"
    assert manifest.tier == "FREEMIUM"
    assert manifest.auth_type == "api_key"


def test_tile_styles_defined() -> None:
    styles = MapboxConfig().tile_styles
    assert set(styles.keys()) == {"satellite", "satellite_streets", "dark", "outdoors", "streets"}


def test_saudi_bounds_defined() -> None:
    bounds = MapboxConfig().saudi_tile_bounds
    assert len(bounds) == 7
    assert bounds["riyadh_metro"]["north"] == 25.0


def test_tile_bounds_from_zxy() -> None:
    b = MapboxNormalizer().tile_bounds_from_zxy(1, 1, 1)
    assert round(b["north"], 4) == 0.0
    assert round(b["west"], 4) == 0.0
    assert round(b["east"], 4) == 180.0


def test_zoom_resolution_mapping() -> None:
    n = MapboxNormalizer()
    assert 9.0 <= n.zoom_to_resolution_m(14) <= 11.0
    assert 35.0 <= n.zoom_to_resolution_m(12) <= 45.0


def test_download_size_estimate() -> None:
    cfg = MapboxConfig()
    est = MapboxNormalizer().estimate_download_size(cfg.saudi_tile_bounds["riyadh_metro"], 0, 14)
    assert est["tile_count"] > 100
    assert est["estimated_mb"] > 1.0


def test_geocode_country_restriction() -> None:
    assert MapboxConfig().geocoding_countries == "SA,YE,OM,AE,KW,BH,QA"


def test_geocode_bilingual() -> None:
    fixture = json.loads((FIXTURE_DIR / "geocode_riyadh.json").read_text(encoding="utf-8"))
    normalized = MapboxNormalizer().normalize_geocode_result(fixture["features"][0])
    assert normalized["place_name_en"] == "Riyadh"
    assert normalized["place_name_ar"] == "الرياض"


def test_normalize_route_distance() -> None:
    fixture = json.loads((FIXTURE_DIR / "route_riyadh_jeddah.json").read_text(encoding="utf-8"))
    route = MapboxNormalizer().normalize_route(fixture["routes"][0])
    assert 930 <= route["distance_km"] <= 980


def test_airgapped_routing_fallback() -> None:
    result = MapboxAdapter(mode="airgapped").get_route((46.6753, 24.7136), (39.1925, 21.4858))
    assert result is not None
    assert result["route"] is None
    assert "PathPlanner" in result["note"]


def test_fetch_airgapped_reads_cache(tmp_path: Path) -> None:
    adapter = MapboxAdapter(mode="airgapped")
    adapter.cache_root = tmp_path
    tile_path = tmp_path / "satellite" / "1" / "1" / "1.jpg"
    tile_path.parent.mkdir(parents=True, exist_ok=True)
    tile_path.write_bytes(b"tile")
    assert adapter.fetch_tile(1, 1, 1, style="satellite") == b"tile"


def test_health_check_structure() -> None:
    health = MapboxAdapter(mode="airgapped").health_check()
    assert {"status", "latency", "detail", "mode"}.issubset(health.keys())
