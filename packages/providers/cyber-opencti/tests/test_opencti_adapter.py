from __future__ import annotations

import importlib


def _load():
    adapter_mod = importlib.import_module("packages.providers.cyber-opencti.adapter")
    norm_mod = importlib.import_module("packages.providers.cyber-opencti.normalizer")
    return adapter_mod.OpenCTIAdapter, norm_mod.OpenCTINormalizer


def test_manifest_correct():
    Adapter, _ = _load()
    m = Adapter(mode="airgapped").get_manifest()
    assert m.provider_id == "cyber-opencti"
    assert m.tier.value == "FREE"
    assert m.auth_type == "api_key"
    assert m.category.value == "CYBER_THREAT_INTEL"


def test_stix_pattern_parsing_ipv4():
    _, N = _load()
    assert N().parse_stix_pattern("[ipv4-addr:value = '192.168.1.1']") == ("ip", "192.168.1.1")


def test_stix_pattern_parsing_domain():
    _, N = _load()
    assert N().parse_stix_pattern("[domain-name:value = 'evil.com']") == ("domain", "evil.com")


def test_stix_pattern_parsing_sha256():
    _, N = _load()
    assert N().parse_stix_pattern("[file:hashes.'SHA-256' = 'abc']") == ("hash_sha256", "abc")


def test_opencti_score_to_severity():
    _, N = _load()
    n = N()
    assert n._score_to_severity(90) == "critical"
    assert n._score_to_severity(70) == "high"
    assert n._score_to_severity(50) == "medium"
    assert n._score_to_severity(20) == "low"


def test_kill_chain_to_mitre():
    _, N = _load()
    node = {"pattern": "[ipv4-addr:value = '1.1.1.1']", "x_opencti_score": 50, "killChainPhases": [{"phase_name": "T1566"}], "objectLabel": [], "createdBy": {"name": "OpenCTI"}}
    out = N().normalize_indicator(node)
    assert "T1566" in out.mitre_techniques


def test_normalize_batch():
    Adapter, _ = _load()
    a = Adapter(mode="airgapped")
    out = a.normalize(a.fetch({"endpoint": "indicators"}))
    assert len(out) == 15


def test_threat_actor_normalization():
    _, N = _load()
    actor = {"name": "Desert Jackal", "aliases": ["DJ"], "primary_motivation": "espionage", "sophistication": "advanced", "objectLabel": [{"value": "apt"}]}
    out = N().normalize_threat_actor(actor)
    assert out["name"] == "Desert Jackal"
    assert out["aliases"] == ["DJ"]
    assert out["motivation"] == "espionage"


def test_fetch_airgapped():
    Adapter, _ = _load()
    out = Adapter(mode="airgapped").fetch({"endpoint": "indicators", "limit": 5})
    assert out["count"] == 5
