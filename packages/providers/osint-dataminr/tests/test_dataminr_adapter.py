from __future__ import annotations

import importlib


def _load():
    mod = importlib.import_module("packages.providers.osint-dataminr.adapter")
    return mod.DataminrAdapter


def test_manifest_correct() -> None:
    Adapter = _load()
    m = Adapter(mode="airgapped").get_manifest()
    assert m.provider_id == "osint-dataminr"
    assert m.tier == "PREMIUM"
    assert m.auth_type == "oauth2"


def test_alert_type_to_severity_mapping() -> None:
    Adapter = _load()
    n = Adapter(mode="airgapped").normalizer
    assert n.severity_from_alert_type("flash") == "critical"
    assert n.severity_from_alert_type("urgentAlert") == "high"
    assert n.severity_from_alert_type("alert") == "medium"


def test_geo_extraction() -> None:
    Adapter = _load()
    adapter = Adapter(mode="airgapped")
    alert = adapter.get_alerts(limit=1)["alerts"][0]
    event = adapter.normalizer.normalize_alert(alert)
    assert event.geo_point is not None


def test_watchlist_handling() -> None:
    Adapter = _load()
    watchlists = Adapter(mode="airgapped").list_watchlists()
    assert len(watchlists) == 5


def test_flash_filter() -> None:
    Adapter = _load()
    flash = Adapter(mode="airgapped").get_flash_alerts()
    assert flash["count"] == 1


def test_fetch_airgapped() -> None:
    Adapter = _load()
    out = Adapter(mode="airgapped").fetch({"endpoint": "alerts", "limit": 8})
    assert out["count"] == 8
