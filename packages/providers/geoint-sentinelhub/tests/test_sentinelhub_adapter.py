from __future__ import annotations

import json
import os
import sys
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))))

from packages.providers.geoint_sentinelhub.adapter import SentinelHubAdapter
from packages.providers.geoint_sentinelhub.config import SentinelHubConfig
from packages.providers.geoint_sentinelhub import evalscripts


FIXTURE_DIR = Path(__file__).resolve().parents[1] / "fixtures"


def test_manifest_correct() -> None:
    manifest = SentinelHubAdapter(mode="airgapped").get_manifest()
    assert manifest.provider_id == "geoint-sentinelhub"
    assert manifest.category == "GEOINT"
    assert manifest.tier == "FREEMIUM"
    assert manifest.auth_type == "oauth2"


def test_evalscripts_valid() -> None:
    scripts = [
        evalscripts.SAR_SHIP_ENHANCEMENT,
        evalscripts.TRUE_COLOR_S2,
        evalscripts.NDVI,
        evalscripts.NDWI,
        evalscripts.DUST_AEROSOL,
        evalscripts.THERMAL_HOTSPOT,
    ]
    assert all(isinstance(s, str) and s.strip().startswith("//VERSION=3") for s in scripts)


def test_fetch_catalog_airgapped() -> None:
    data = SentinelHubAdapter(mode="airgapped").fetch_catalog("sentinel-1-grd", None, 7, aoi="persian_gulf")
    assert "features" in data
    assert len(data["features"]) == 3


def test_normalize_catalog_stac_feature() -> None:
    adapter = SentinelHubAdapter(mode="airgapped")
    fixture = json.loads((FIXTURE_DIR / "catalog_search_response.json").read_text(encoding="utf-8"))
    obs = adapter.normalizer.normalize_catalog_result(fixture["features"][0]).to_dict()
    assert obs["provider_id"] == "geoint-sentinelhub"
    assert obs["observation_type"] in {"sar", "multispectral"}


def test_normalize_statistics() -> None:
    adapter = SentinelHubAdapter(mode="airgapped")
    fixture = json.loads((FIXTURE_DIR / "statistics_response.json").read_text(encoding="utf-8"))
    stats = adapter.normalizer.normalize_statistics(fixture)
    assert len(stats) == 6
    assert {"from", "to", "min", "max", "mean", "stdev"}.issubset(stats[0].keys())


def test_sar_ship_evalscript_present() -> None:
    cfg = SentinelHubConfig()
    assert "sar_ship_enhancement" in cfg.evalscripts


def test_saudi_aois_present() -> None:
    cfg = SentinelHubConfig()
    for key in ["full_saudi", "persian_gulf", "red_sea", "eastern_province"]:
        assert key in cfg.saudi_aois


def test_health_check_structure() -> None:
    health = SentinelHubAdapter(mode="airgapped").health_check()
    assert {"status", "latency", "detail"}.issubset(health.keys())
