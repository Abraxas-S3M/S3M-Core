from __future__ import annotations

import os
import sys
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))))

from packages.providers.geoint_nasa_earthdata.adapter import NASAEarthdataAdapter
from packages.providers.geoint_nasa_earthdata.normalizer import NASAEarthdataNormalizer


FIXTURE_CSV = Path(__file__).resolve().parents[1] / "fixtures" / "firms_viirs_saudi_response.csv"


def test_manifest_correct() -> None:
    manifest = NASAEarthdataAdapter(mode="airgapped").get_manifest()
    assert manifest.provider_id == "geoint-nasa-earthdata"
    assert manifest.tier == "FREE"
    assert manifest.auth_type == "api_key"


def test_firms_csv_parsing() -> None:
    adapter = NASAEarthdataAdapter(mode="airgapped")
    records = adapter._parse_firms_csv(FIXTURE_CSV.read_text(encoding="utf-8"), "VIIRS_SNPP_NRT")
    assert len(records) == 15
    assert {"latitude", "longitude", "acq_datetime", "confidence"}.issubset(records[0].keys())


def test_normalize_fire_observation_type() -> None:
    sample = NASAEarthdataAdapter(mode="airgapped").fetch_active_fires()["fires"][0]
    assert NASAEarthdataAdapter(mode="airgapped").normalizer.normalize_fire(sample).observation_type == "thermal"


def test_normalize_confidence_mapping() -> None:
    n = NASAEarthdataNormalizer()
    assert n.map_confidence("low") == 0.3
    assert n.map_confidence("nominal") == 0.7
    assert n.map_confidence("high") == 0.95


def test_normalize_satellite_mapping() -> None:
    n = NASAEarthdataNormalizer()
    assert n.map_satellite("N") == "Suomi NPP"
    assert n.map_satellite("1") == "NOAA-20"


def test_normalize_resolution() -> None:
    n = NASAEarthdataNormalizer()
    assert n.map_resolution("VIIRS_SNPP_NRT") == 375.0
    assert n.map_resolution("MODIS_NRT") == 1000.0


def test_filter_by_confidence() -> None:
    adapter = NASAEarthdataAdapter(mode="airgapped")
    recs = adapter._parse_firms_csv(FIXTURE_CSV.read_text(encoding="utf-8"), "VIIRS_SNPP_NRT")
    filtered = adapter.normalizer.filter_by_confidence(recs, "nominal")
    assert all(item["confidence"] in {"nominal", "high"} for item in filtered)


def test_fetch_airgapped() -> None:
    data = NASAEarthdataAdapter(mode="airgapped").fetch_active_fires("full_saudi", 1)
    assert data["count"] > 0


def test_saudi_region_codes() -> None:
    cfg = NASAEarthdataAdapter(mode="airgapped").config
    assert len(cfg.saudi_region_codes) == 9
    for code in ["SAU", "YEM", "OMN", "ARE", "KWT", "BHR", "QAT", "IRQ", "IRN"]:
        assert code in cfg.saudi_region_codes


def test_fire_coordinates_valid() -> None:
    normalized = NASAEarthdataAdapter(mode="airgapped").fetch_and_normalize({"aoi": "full_saudi", "days": 1})
    for obs in normalized["observations"]:
        assert -90 <= obs.geo_point.lat <= 90
        assert -180 <= obs.geo_point.lon <= 180
