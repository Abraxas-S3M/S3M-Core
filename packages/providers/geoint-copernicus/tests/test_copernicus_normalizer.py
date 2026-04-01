"""Tests for Copernicus normalizer field and geometry mapping."""

from __future__ import annotations

import json
from pathlib import Path

from packages.providers.geoint_copernicus.normalizer import CopernicusNormalizer


def _load_fixture(name: str) -> dict:
    fixture_path = (
        Path(__file__).resolve().parent.parent / "fixtures" / name
    )
    with fixture_path.open("r", encoding="utf-8") as f:
        return json.load(f)


def test_normalize_product_fields():
    normalizer = CopernicusNormalizer()
    product = _load_fixture("sentinel1_search_response.json")["value"][0]
    obs = normalizer.normalize_product(product)
    assert obs.record_id
    assert obs.observation_type == "sar"
    assert obs.satellite.startswith("Sentinel-1")
    assert obs.acquisition_time == "2024-06-15T02:45:30.000Z"
    assert obs.footprint
    assert obs.provenance is not None
    assert obs.tags


def test_provenance_correct():
    normalizer = CopernicusNormalizer()
    product = _load_fixture("sentinel1_search_response.json")["value"][0]
    obs = normalizer.normalize_product(product)
    assert obs.provenance is not None
    assert obs.provenance.provider_id == "geoint-copernicus"
    assert obs.provenance.provider_name == "Copernicus/ESA"
    assert obs.provenance.confidence == 1.0


def test_bands_sentinel1():
    normalizer = CopernicusNormalizer()
    product = _load_fixture("sentinel1_search_response.json")["value"][0]
    obs = normalizer.normalize_product(product)
    assert obs.bands == ["VV", "VH"]


def test_bands_sentinel2():
    normalizer = CopernicusNormalizer()
    product = _load_fixture("sentinel2_search_response.json")["value"][0]
    obs = normalizer.normalize_product(product)
    assert obs.bands == [
        "B01",
        "B02",
        "B03",
        "B04",
        "B05",
        "B06",
        "B07",
        "B08",
        "B8A",
        "B09",
        "B10",
        "B11",
        "B12",
    ]


def test_observation_type_mapping():
    normalizer = CopernicusNormalizer()
    s1 = {"Name": "S1A_IW_GRDH_1SDV_TEST.SAFE", "Id": "1"}
    s2 = {"Name": "S2A_MSIL2A_TEST.SAFE", "Id": "2"}
    s3 = {"Name": "S3A_TEST.SAFE", "Id": "3"}
    s5 = {"Name": "S5P_TEST.SAFE", "Id": "4"}
    assert normalizer.normalize_product(s1).observation_type == "sar"
    assert normalizer.normalize_product(s2).observation_type == "multispectral"
    assert normalizer.normalize_product(s3).observation_type == "thermal"
    assert normalizer.normalize_product(s5).observation_type == "atmospheric"


def test_satellite_name_extraction():
    normalizer = CopernicusNormalizer()
    product = {
        "Id": "1",
        "Name": "S1A_IW_GRDH_1SDV_20240615T024530_20240615T024555_054321_069ABC_1234.SAFE",
    }
    obs = normalizer.normalize_product(product)
    assert obs.satellite == "Sentinel-1A"


def test_wkt_polygon_parsing():
    normalizer = CopernicusNormalizer()
    wkt = "POLYGON((48 24, 56 24, 56 30, 48 30, 48 24))"
    points = normalizer.parse_wkt_polygon(wkt)
    assert len(points) == 5
    assert points[0].lat == 24.0
    assert points[0].lon == 48.0
    assert points[2].lat == 30.0
    assert points[2].lon == 56.0


def test_wkt_lon_lat_swap():
    normalizer = CopernicusNormalizer()
    points = normalizer.parse_wkt_polygon("POLYGON((49.5 25.0, 51.0 25.0, 51.0 27.0, 49.5 27.0, 49.5 25.0))")
    assert points[0].lat == 25.0
    assert points[0].lon == 49.5
