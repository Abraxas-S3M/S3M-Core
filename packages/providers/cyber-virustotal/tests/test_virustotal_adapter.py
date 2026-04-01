from __future__ import annotations

import importlib


def _load():
    am = importlib.import_module("packages.providers.cyber-virustotal.adapter")
    nm = importlib.import_module("packages.providers.cyber-virustotal.normalizer")
    return am.VirusTotalAdapter, nm.VirusTotalNormalizer


def test_manifest_correct():
    A, _ = _load()
    m = A(mode="airgapped").get_manifest()
    assert m.tier.value == "FREEMIUM"
    assert m.auth_type == "api_key"
    assert m.rate_limit_rpm == 4


def test_reputation_score_mapping():
    _, N = _load()
    n = N()
    assert n._map_vt_reputation(-100) == 100
    assert n._map_vt_reputation(100) == 0


def test_severity_from_malicious_count():
    _, N = _load()
    n = N()
    assert n.compute_severity(12) == "critical"
    assert n.compute_severity(5) == "high"
    assert n.compute_severity(1) == "medium"
    assert n.compute_severity(0) == "low"


def test_normalize_malicious_ip():
    A, _ = _load()
    a = A(mode="airgapped")
    out = a.normalizer.normalize_ip_report(a._load_fixture_json("ip_report_malicious.json"))
    assert out.severity == "critical"


def test_normalize_benign_ip():
    A, _ = _load()
    a = A(mode="airgapped")
    out = a.normalizer.normalize_ip_report(a._load_fixture_json("ip_report_benign.json"))
    assert out.severity == "low"
    assert out.threat_type == "benign"


def test_normalize_hash_report():
    A, _ = _load()
    a = A(mode="airgapped")
    out = a.normalizer.normalize_hash_report(a._load_fixture_json("hash_report_malware.json"))
    assert out.indicator_type == "hash_sha256"
    assert any(tag.startswith("file_type:") for tag in out.tags)


def test_rate_limit_strict():
    A, _ = _load()
    assert A(mode="airgapped").config.rate_limit_rpm == 4


def test_fetch_airgapped():
    A, _ = _load()
    out = A(mode="airgapped").fetch({"type": "ip", "value": "1.1.1.1"})
    assert "data" in out
