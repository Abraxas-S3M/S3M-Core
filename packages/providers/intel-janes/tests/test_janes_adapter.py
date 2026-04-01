from __future__ import annotations

import importlib


def _load():
    mod = importlib.import_module("packages.providers.intel-janes.adapter")
    return mod.JanesAdapter


def test_manifest_correct() -> None:
    Adapter = _load()
    m = Adapter(mode="airgapped").get_manifest()
    assert m.provider_id == "intel-janes"
    assert m.tier == "PREMIUM"
    assert m.auth_type == "api_key"


def test_equipment_normalization() -> None:
    Adapter = _load()
    adapter = Adapter(mode="airgapped")
    equipment = adapter.search_equipment("F-15SA", country="Saudi Arabia")
    normalized = adapter.normalizer.normalize_equipment(equipment)
    assert normalized["name"] == "F-15SA"
    assert normalized["phase17_asset_registry_link"] is True


def test_orbat_structure_phase16_link() -> None:
    Adapter = _load()
    adapter = Adapter(mode="airgapped")
    orbat = adapter.get_orbat("SA")
    normalized = adapter.normalizer.normalize_orbat(orbat)
    assert normalized["phase16_orbat_compatible"] is True
    assert len(normalized["units"]) >= 1


def test_threat_assessment_normalized_global_event() -> None:
    Adapter = _load()
    adapter = Adapter(mode="airgapped")
    threat = adapter.get_threat_assessment("middle-east")
    event = adapter.normalizer.normalize_threat(threat)
    assert event.event_type == "threat_assessment"
    assert event.provenance.confidence == 0.95


def test_news_normalization() -> None:
    Adapter = _load()
    adapter = Adapter(mode="airgapped")
    news = adapter.get_defense_news("middle-east", 7)
    events = [adapter.normalizer.normalize_news(article) for article in news["articles"]]
    assert events[0].event_type == "defense_analysis"


def test_fetch_airgapped() -> None:
    Adapter = _load()
    out = Adapter(mode="airgapped").fetch({"endpoint": "equipment", "query": "F-15SA"})
    assert out["name"] == "F-15SA"
