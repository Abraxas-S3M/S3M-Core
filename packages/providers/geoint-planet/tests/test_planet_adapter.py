from __future__ import annotations

import importlib


def _load():
    mod = importlib.import_module("packages.providers.geoint-planet.adapter")
    return mod.PlanetAdapter


def test_manifest_correct() -> None:
    Adapter = _load()
    m = Adapter(mode="airgapped").get_manifest()
    assert m.provider_id == "geoint-planet"
    assert m.tier == "PREMIUM"
    assert m.auth_type == "api_key"


def test_resolution_psscene() -> None:
    Adapter = _load()
    adapter = Adapter(mode="airgapped")
    scene = adapter.search({"type": "Polygon", "coordinates": [[[46, 24], [50, 24], [50, 28], [46, 28], [46, 24]]]}, "2024-06-01", "2024-06-15", item_type="PSScene", limit=1)["scenes"][0]
    normalized = adapter.normalizer.normalize_scene(scene)
    assert normalized.resolution_m == 3.0


def test_resolution_skysat() -> None:
    Adapter = _load()
    adapter = Adapter(mode="airgapped")
    scene = adapter.search({"type": "Polygon", "coordinates": [[[56.0, 26.0], [56.4, 26.0], [56.4, 26.3], [56.0, 26.3], [56.0, 26.0]]]}, "2024-06-01", "2024-06-15", item_type="SkySatScene", limit=1)["scenes"][0]
    normalized = adapter.normalizer.normalize_scene(scene)
    assert normalized.resolution_m == 0.5


def test_daily_coverage_concept() -> None:
    Adapter = _load()
    coverage = Adapter(mode="airgapped").search_daily_coverage("persian_gulf", 7)
    assert coverage["daily_revisit_expected"] is True
    assert coverage["scene_count"] >= 7


def test_search_filter_construction() -> None:
    Adapter = _load()
    adapter = Adapter(mode="airgapped")
    filter_payload = adapter._build_search_filter({"type": "Polygon", "coordinates": []}, "2024-06-01T00:00:00Z", "2024-06-02T00:00:00Z", 0.2)
    config = filter_payload["config"]
    assert any(item["type"] == "GeometryFilter" for item in config)
    assert any(item["type"] == "DateRangeFilter" for item in config)
    assert any(item["type"] == "RangeFilter" for item in config)


def test_normalize_scene_all_fields() -> None:
    Adapter = _load()
    adapter = Adapter(mode="airgapped")
    scene = adapter.search({"type": "Polygon", "coordinates": [[[46, 24], [50, 24], [50, 28], [46, 28], [46, 24]]]}, "2024-06-01", "2024-06-15", limit=1)["scenes"][0]
    obs = adapter.normalizer.normalize_scene(scene)
    assert obs.observation_type == "optical"
    assert obs.provenance.confidence == 0.95
    assert "premium" in obs.tags


def test_fetch_airgapped() -> None:
    Adapter = _load()
    out = Adapter(mode="airgapped").fetch({"endpoint": "search", "item_type": "PSScene", "limit": 3})
    assert out["count"] == 3
