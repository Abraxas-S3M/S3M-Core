from __future__ import annotations

import importlib


def _load():
    mod = importlib.import_module("packages.providers.geoint-capella.adapter")
    return mod.CapellaAdapter


def test_manifest_correct() -> None:
    Adapter = _load()
    manifest = Adapter(mode="airgapped").get_manifest()
    assert manifest.provider_id == "geoint-capella"
    assert manifest.tier == "PREMIUM"
    assert manifest.auth_type == "oauth2"


def test_always_sar() -> None:
    Adapter = _load()
    adapter = Adapter(mode="airgapped")
    scene = adapter.search_catalog([56.0, 26.0, 56.5, 26.5], "2024-06-01", "2024-06-15", limit=1)["scenes"][0]
    obs = adapter.normalizer.normalize_scene(scene)
    assert obs.observation_type == "sar"


def test_resolution_spotlight() -> None:
    Adapter = _load()
    adapter = Adapter(mode="airgapped")
    scene = adapter.search_catalog([56.0, 26.0, 56.5, 26.5], "2024-06-01", "2024-06-15", limit=1)["scenes"][0]
    obs = adapter.normalizer.normalize_scene(scene)
    assert obs.resolution_m == 0.25


def test_all_weather_tags() -> None:
    Adapter = _load()
    adapter = Adapter(mode="airgapped")
    scene = adapter.search_catalog([56.0, 26.0, 56.5, 26.5], "2024-06-01", "2024-06-15", limit=1)["scenes"][0]
    obs = adapter.normalizer.normalize_scene(scene)
    assert "all_weather" in obs.tags
    assert "night_capable" in obs.tags
    assert "cloud_penetrating" in obs.tags


def test_fetch_airgapped() -> None:
    Adapter = _load()
    out = Adapter(mode="airgapped").fetch({"endpoint": "catalog", "limit": 3})
    assert out["count"] == 3
