from __future__ import annotations

import importlib


def _load():
    am = importlib.import_module("packages.providers.cyber-abuseipdb.adapter")
    nm = importlib.import_module("packages.providers.cyber-abuseipdb.normalizer")
    return am.AbuseIPDBAdapter, nm.AbuseIPDBNormalizer


def test_manifest_correct():
    A, _ = _load()
    m = A(mode="airgapped").get_manifest()
    assert m.tier.value == "FREEMIUM"
    assert m.auth_type == "api_key"


def test_confidence_to_severity():
    _, N = _load()
    n = N()
    assert n._severity(92) == "critical"
    assert n._severity(55) == "high"
    assert n._severity(25) == "medium"
    assert n._severity(5) == "low"


def test_abuse_category_mapping():
    _, N = _load()
    labels = N().map_abuse_categories([14, 18, 22])
    assert "Port Scan" in labels
    assert "Brute-Force" in labels
    assert "SSH" in labels


def test_normalize_malicious_ip():
    A, _ = _load()
    a = A(mode="airgapped")
    out = a.normalizer.normalize_ip_check(a._load_fixture_json("ip_check_malicious.json")["data"])
    assert out.severity == "critical"
    assert "brute_force" in out.threat_type


def test_normalize_clean_ip():
    A, _ = _load()
    a = A(mode="airgapped")
    out = a.normalizer.normalize_ip_check(a._load_fixture_json("ip_check_clean.json")["data"])
    assert out.severity == "low"


def test_blacklist_normalize_batch():
    A, _ = _load()
    a = A(mode="airgapped")
    out = a.normalizer.normalize_blacklist(a._load_fixture_json("blacklist_response.json")["data"])
    assert len(out) == 10


def test_fetch_airgapped():
    A, _ = _load()
    out = A(mode="airgapped").fetch({"type": "ip", "value": "8.8.8.8"})
    assert "data" in out
