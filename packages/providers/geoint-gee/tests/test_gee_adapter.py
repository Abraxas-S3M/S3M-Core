from __future__ import annotations

import json
import os
import sys
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))))

from packages.providers.geoint_gee.adapter import GEEAdapter
from packages.providers.geoint_gee.config import COLLECTIONS


FIXTURE_DIR = Path(__file__).resolve().parents[1] / "fixtures"


def test_manifest_correct() -> None:
    manifest = GEEAdapter(mode="airgapped").get_manifest()
    assert manifest.provider_id == "geoint-gee"
    assert manifest.tier == "FREE"
    assert manifest.auth_type == "service_account"


def test_collections_defined() -> None:
    assert len(COLLECTIONS) == 7
    for key in ["sentinel1_sar", "sentinel2_optical", "viirs_nighttime", "modis_temperature", "surface_water", "srtm_elevation", "landsat9"]:
        assert key in COLLECTIONS


def test_validate_credentials_airgapped(tmp_path: Path) -> None:
    (tmp_path / "export.tif").write_text("fixture", encoding="utf-8")
    assert GEEAdapter(mode="airgapped", export_dir=str(tmp_path)).validate_credentials() is True


def test_validate_credentials_missing_key(monkeypatch) -> None:
    monkeypatch.delenv("GEE_SERVICE_ACCOUNT_KEY_PATH", raising=False)
    monkeypatch.delenv("S3M_GEE_SERVICE_ACCOUNT_KEY_PATH", raising=False)
    assert GEEAdapter(mode="online").validate_credentials() is False


def test_fetch_airgapped_lists_exports() -> None:
    data = GEEAdapter(mode="airgapped").fetch({"query": "exports"})
    assert "exports" in data
    assert len(data["exports"]) >= 1


def test_normalize_sentinel2_observation_type() -> None:
    metadata = json.loads((FIXTURE_DIR / "export_metadata.json").read_text(encoding="utf-8"))["exports"][0]
    assert GEEAdapter(mode="airgapped").normalizer.normalize_export_metadata(metadata).observation_type == "multispectral"


def test_normalize_viirs_observation_type() -> None:
    metadata = json.loads((FIXTURE_DIR / "export_metadata.json").read_text(encoding="utf-8"))["exports"][1]
    assert GEEAdapter(mode="airgapped").normalizer.normalize_export_metadata(metadata).observation_type == "nighttime_radiance"


def test_normalize_srtm_observation_type() -> None:
    metadata = json.loads((FIXTURE_DIR / "export_metadata.json").read_text(encoding="utf-8"))["exports"][2]
    assert GEEAdapter(mode="airgapped").normalizer.normalize_export_metadata(metadata).observation_type == "elevation"


def test_normalize_resolution_mapping() -> None:
    fixture = json.loads((FIXTURE_DIR / "export_metadata.json").read_text(encoding="utf-8"))["exports"]
    resolutions = [GEEAdapter(mode="airgapped").normalizer.normalize_export_metadata(item).resolution_m for item in fixture]
    assert 10.0 in resolutions and 500.0 in resolutions and 30.0 in resolutions


def test_change_detection_result_structure() -> None:
    result = GEEAdapter(mode="airgapped").normalize(GEEAdapter(mode="airgapped").fetch_change_detection("full_saudi", 2020, 2026))
    assert {"baseline_date", "change_magnitude", "change_type"}.issubset(result.keys())


def test_nighttime_lights_structure() -> None:
    result = GEEAdapter(mode="airgapped").normalize(GEEAdapter(mode="airgapped").fetch_nighttime_lights("eastern_province", 30))
    assert "radiance_mean" in result and "lit_area" in result and "dark_area" in result


def test_health_check_airgapped(tmp_path: Path) -> None:
    new_file = tmp_path / "fresh_export.json"
    new_file.write_text("{}", encoding="utf-8")
    assert GEEAdapter(mode="airgapped", export_dir=str(tmp_path)).health_check()["status"] == "ok"

    old_epoch = 1577836800
    os.utime(new_file, (old_epoch, old_epoch))
    old_file = tmp_path / "old_export.json"
    old_file.write_text("{}", encoding="utf-8")
    os.utime(old_file, (old_epoch, old_epoch))
    assert GEEAdapter(mode="airgapped", export_dir=str(tmp_path)).health_check()["status"] == "degraded"


def test_airgap_note_in_manifest() -> None:
    assert "air-gapped" in GEEAdapter(mode="airgapped").get_manifest().description.lower()
