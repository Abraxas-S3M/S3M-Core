from __future__ import annotations

import importlib


def _load():
    mod = importlib.import_module("packages.providers.cyber-recordedfuture.adapter")
    return mod.RecordedFutureAdapter


def test_manifest_correct() -> None:
    Adapter = _load()
    m = Adapter(mode="airgapped").get_manifest()
    assert m.provider_id == "cyber-recordedfuture"
    assert m.tier == "PREMIUM"
    assert m.auth_type == "api_key"


def test_risk_to_severity_mapping() -> None:
    Adapter = _load()
    adapter = Adapter(mode="airgapped")
    high = adapter.lookup_ip("185.220.101.14")
    low = adapter.lookup_domain("example.org")
    assert adapter.normalizer.normalize_entity(high).severity == "critical"
    assert adapter.normalizer.normalize_entity(low).severity == "low"


def test_threat_actor_normalization() -> None:
    Adapter = _load()
    actor = Adapter(mode="airgapped").search_threat_actors("APT")
    normalized = Adapter(mode="airgapped").normalizer.normalize_threat_actor(actor)
    assert "aliases" in normalized and "ttps" in normalized


def test_cve_enrichment() -> None:
    Adapter = _load()
    cve = Adapter(mode="airgapped").lookup_cve("CVE-2024-3400")
    indicator = Adapter(mode="airgapped").normalizer.normalize_entity(cve)
    assert indicator.indicator_type == "vulnerability"
    assert indicator.severity == "critical"


def test_fetch_airgapped() -> None:
    Adapter = _load()
    out = Adapter(mode="airgapped").fetch({"endpoint": "ip", "value": "185.220.101.14"})
    assert out["risk_score"] == 87
