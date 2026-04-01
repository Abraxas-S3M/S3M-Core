from __future__ import annotations

import importlib


def _load():
    mod = importlib.import_module("packages.providers.geoint-iceye.adapter")
    return mod.ICEYEAdapter


def test_manifest_correct() -> None:
    Adapter = _load()
    manifest = Adapter(mode="airgapped").get_manifest()
    assert manifest.provider_id == "geoint-iceye"
    assert manifest.tier == "PREMIUM"
    assert manifest.auth_type == "api_key"


def test_always_sar() -> None:
    Adapter = _load()
    scene = Adapter(mode="airgapped").search_catalog([55.8, 25.8, 56.7, 26.6], "2024-06-01", "2024-06-15", limit=1)["scenes"][0]
    obs = Adapter(mode="airgapped").normalizer.normalize_scene(scene)
    assert obs.observation_type == "sar"


def test_change_detection_structure() -> None:
    Adapter = _load()
    data = Adapter(mode="airgapped").run_change_detection("ICEYE-GEO-20240601-001", "ICEYE-GEO-20240610-005")
    normalized = Adapter(mode="airgapped").normalizer.normalize_change_detection(data)
    assert {"changes", "change_area_km2", "change_type"}.issubset(normalized.keys())


def test_change_type_supported() -> None:
    Adapter = _load()
    data = Adapter(mode="airgapped").run_change_detection("ICEYE-GEO-20240601-001", "ICEYE-GEO-20240610-005")
    assert data["change_type"] in {"new_construction", "destruction", "vehicle_movement", "water_level_change"}


def test_flood_mapping_structure() -> None:
    Adapter = _load()
    flood = Adapter(mode="airgapped").run_flood_mapping("ICEYE-GEO-20240610-005")
    assert {"flood_extent_km2", "flood_polygon", "severity"}.issubset(flood.keys())


def test_confidence_from_sar_source() -> None:
    Adapter = _load()
    scene = Adapter(mode="airgapped").search_catalog([55.8, 25.8, 56.7, 26.6], "2024-06-01", "2024-06-15", limit=1)["scenes"][0]
    obs = Adapter(mode="airgapped").normalizer.normalize_scene(scene)
    assert obs.provenance.confidence == 0.96


def test_fetch_airgapped() -> None:
    Adapter = _load()
    out = Adapter(mode="airgapped").fetch({"endpoint": "catalog", "limit": 2})
    assert out["count"] == 2
