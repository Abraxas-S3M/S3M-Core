from __future__ import annotations

import json
import os
import sys
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))))

from packages.providers.gis_osm.adapter import OSMAdapter
from packages.providers.gis_osm.config import OSMConfig
from packages.providers.gis_osm.normalizer import OSMNormalizer


FIXTURE_DIR = Path(__file__).resolve().parents[1] / "fixtures"


def test_manifest_correct() -> None:
    manifest = OSMAdapter(mode="airgapped").get_manifest()
    assert manifest.provider_id == "gis-osm"
    assert manifest.tier == "FREE"
    assert manifest.auth_type == "none"


def test_no_auth_required() -> None:
    assert OSMAdapter(mode="online").validate_credentials() is True


def test_military_queries_defined() -> None:
    queries = OSMConfig().military_queries
    assert len(queries) == 11
    for key in ["roads", "buildings", "military", "airports", "ports", "bridges", "tunnels", "water", "landuse", "power", "fuel_stations"]:
        assert key in queries


def test_overpass_query_construction() -> None:
    adapter = OSMAdapter(mode="airgapped")
    bounds = OSMConfig().saudi_bounds["riyadh_metro"]
    rendered = adapter._render_query(adapter.config.military_queries["roads"], bounds)
    assert "24.4,46.3,25.0,47.1" in rendered


def test_normalize_road() -> None:
    fixture = json.loads((FIXTURE_DIR / "overpass_roads_riyadh.json").read_text(encoding="utf-8"))
    road = OSMNormalizer().normalize_road(fixture["elements"][0])
    assert road["highway_class"] in {"motorway", "primary", "secondary"}
    assert road["name_en"] is not None
    assert road["name_ar"] is not None


def test_bilingual_name_extraction() -> None:
    tags = {"name": "King Fahd Road", "name:ar": "طريق الملك فهد"}
    en, ar = OSMNormalizer().extract_bilingual_names(tags)
    assert en == "King Fahd Road"
    assert ar == "طريق الملك فهد"


def test_normalize_military_feature() -> None:
    fixture = json.loads((FIXTURE_DIR / "overpass_military_saudi.json").read_text(encoding="utf-8"))
    layer = OSMNormalizer().normalize_feature(fixture["elements"][0])
    assert layer.layer_type == "military"


def test_normalize_airport() -> None:
    fixture = json.loads((FIXTURE_DIR / "overpass_airports_saudi.json").read_text(encoding="utf-8"))
    layer = OSMNormalizer().normalize_feature(fixture["elements"][0])
    assert layer.layer_type == "airport"


def test_pbf_download_urls() -> None:
    cfg = OSMConfig()
    assert cfg.pbf_downloads["gcc_states"].endswith("gcc-states-latest.osm.pbf")
    assert cfg.pbf_downloads["saudi_arabia"].endswith("saudi-arabia-latest.osm.pbf")


def test_fetch_airgapped_reads_cache(tmp_path: Path) -> None:
    adapter = OSMAdapter(mode="airgapped")
    adapter.extract_cache = tmp_path
    fixture = json.loads((FIXTURE_DIR / "overpass_roads_riyadh.json").read_text(encoding="utf-8"))
    (tmp_path / "roads.json").write_text(json.dumps(fixture), encoding="utf-8")
    out = adapter.query_overpass('way["highway"](24.4,46.3,25.0,47.1);')
    assert out["count"] >= 1
