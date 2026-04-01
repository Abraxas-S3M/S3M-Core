from __future__ import annotations

import importlib


def _load():
    adapter_mod = importlib.import_module("packages.providers.cyber-misp.adapter")
    norm_mod = importlib.import_module("packages.providers.cyber-misp.normalizer")
    return adapter_mod.MISPThreatIntelAdapter, norm_mod.MISPNormalizer


def test_manifest_correct():
    Adapter, _ = _load()
    m = Adapter(mode="airgapped").get_manifest()
    assert m.provider_id == "cyber-misp"
    assert m.tier.value == "FREE"
    assert m.auth_type == "api_key"
    assert m.category.value == "CYBER_THREAT_INTEL"


def test_attribute_type_mapping():
    _, N = _load()
    n = N()
    assert n.ATTRIBUTE_TYPE_MAP["ip-src"] == "ip"
    assert n.ATTRIBUTE_TYPE_MAP["sha256"] == "hash_sha256"
    assert n.ATTRIBUTE_TYPE_MAP["domain"] == "domain"
    assert n.ATTRIBUTE_TYPE_MAP["vulnerability"] == "cve"


def test_threat_level_mapping():
    _, N = _load()
    n = N()
    assert n._EVENT_SEVERITY[1] == "critical"
    assert n._EVENT_SEVERITY[2] == "high"
    assert n._EVENT_SEVERITY[3] == "medium"
    assert n._EVENT_SEVERITY[4] == "low"


def test_mitre_extraction():
    _, N = _load()
    out = N().extract_mitre_from_tags([{"name": 'misp-galaxy:mitre-attack-pattern="Spearphishing - T1566"'}])
    assert out == ["T1566"]


def test_tlp_extraction():
    _, N = _load()
    assert N().extract_tlp([{"name": "tlp:amber"}]) == "AMBER"


def test_confidence_from_analysis():
    _, N = _load()
    n = N()
    sample = {"type": "ip-src", "value": "1.1.1.1", "timestamp": "1719878400", "Tag": []}
    assert n.normalize_attribute(sample, {"analysis": 0}).confidence == 0.3
    assert n.normalize_attribute(sample, {"analysis": 1}).confidence == 0.6
    assert n.normalize_attribute(sample, {"analysis": 2}).confidence == 0.9


def test_normalize_batch_count():
    Adapter, _ = _load()
    a = Adapter(mode="airgapped")
    attrs = a.fetch({"endpoint": "attributes"})["attributes"]
    events = a.fetch({"endpoint": "events"})["events"]
    em = {str(e["id"]): e for e in events}
    out = a.normalizer.normalize_batch(attrs, event_map=em)
    assert len(out) == 20


def test_fetch_airgapped():
    Adapter, _ = _load()
    out = Adapter(mode="airgapped").fetch({"endpoint": "attributes", "limit": 10})
    assert out["count"] == 10


def test_health_check_structure():
    Adapter, _ = _load()
    health = Adapter(mode="airgapped").health_check()
    assert "status" in health
    assert "detail" in health
