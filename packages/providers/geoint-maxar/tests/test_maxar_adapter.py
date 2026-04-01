from __future__ import annotations

import importlib


def _load():
    adapter_mod = importlib.import_module("packages.providers.geoint-maxar.adapter")
    return adapter_mod.MaxarAdapter


def test_manifest_correct() -> None:
    Adapter = _load()
    manifest = Adapter(mode="airgapped").get_manifest()
    assert manifest.provider_id == "geoint-maxar"
    assert manifest.category == "GEOINT"
    assert manifest.tier == "PREMIUM"
    assert manifest.auth_type == "oauth2"


def test_satellite_specs() -> None:
    Adapter = _load()
    cfg = Adapter(mode="airgapped").config
    assert cfg.satellites["WorldView-3"]["resolution_m"] == 0.31
    assert cfg.satellites["WorldView-2"]["resolution_m"] == 0.46
    assert cfg.satellites["GeoEye-1"]["resolution_m"] == 0.41


def test_normalize_resolution_from_satellite() -> None:
    Adapter = _load()
    adapter = Adapter(mode="airgapped")
    image = adapter.search_catalog([46, 24, 50, 28], "2024-06-01", "2024-06-15", ["worldview-3"], limit=1)["images"][0]
    normalized = adapter.normalizer.normalize_catalog_result(image)
    assert normalized.resolution_m == 0.31


def test_normalize_observation_type_optical() -> None:
    Adapter = _load()
    adapter = Adapter(mode="airgapped")
    image = adapter.search_catalog([46, 24, 50, 28], "2024-06-01", "2024-06-15", limit=1)["images"][0]
    normalized = adapter.normalizer.normalize_catalog_result(image)
    assert normalized.observation_type == "optical"


def test_confidence_defense_grade() -> None:
    Adapter = _load()
    adapter = Adapter(mode="airgapped")
    image = adapter.search_catalog([46, 24, 50, 28], "2024-06-01", "2024-06-15", limit=1)["images"][0]
    normalized = adapter.normalizer.normalize_catalog_result(image)
    assert normalized.provenance.confidence == 0.98


def test_tasking_order_structure() -> None:
    Adapter = _load()
    order = Adapter(mode="airgapped").submit_tasking("POLYGON((56.0 26.0,56.4 26.0,56.4 26.3,56.0 26.3,56.0 26.0))")
    normalized = Adapter(mode="airgapped").normalizer.normalize_tasking_order(order)
    assert {"order_id", "estimated_collection_date", "sensor", "status"}.issubset(normalized.keys())


def test_catalog_search_fixture() -> None:
    Adapter = _load()
    data = Adapter(mode="airgapped").search_catalog([46, 24, 50, 28], "2024-06-01", "2024-06-15", ["worldview-3"], max_cloud=20, limit=10)
    assert data["count"] == 5


def test_fetch_airgapped() -> None:
    Adapter = _load()
    tile = Adapter(mode="airgapped").fetch_imagery_tile("maxar-wv03-20240610-001", 10, 512, 384)
    assert isinstance(tile, bytes)
    assert tile.startswith(b"MAXAR_TILE::")
