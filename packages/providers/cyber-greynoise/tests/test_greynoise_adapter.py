from __future__ import annotations

import importlib


def _load():
    mod = importlib.import_module("packages.providers.cyber-greynoise.adapter")
    return mod.GreyNoiseAdapter


def test_manifest_correct():
    A = _load()
    m = A(mode="airgapped").get_manifest()
    assert m.tier.value == "FREEMIUM"
    assert m.rate_limit_rpm == 3


def test_noise_malicious_classification():
    A = _load()
    a = A(mode="airgapped")
    out = a.normalize(a.check_ip("198.51.100.1"))
    assert out.threat_type == "scanner_malicious"
    assert out.severity == "medium"


def test_noise_benign_classification():
    A = _load()
    a = A(mode="airgapped")
    out = a.normalize(a.check_ip("198.51.100.2"))
    assert out.threat_type == "scanner_benign"
    assert out.severity == "info"


def test_riot_classification():
    A = _load()
    a = A(mode="airgapped")
    out = a.normalize(a.check_ip("8.8.8.8"))
    assert out.threat_type == "known_service"
    assert out.severity == "info"


def test_potentially_targeted():
    A = _load()
    a = A(mode="airgapped")
    out = a.normalize(a.check_ip("203.0.113.200"))
    assert out.threat_type == "potentially_targeted"
    assert out.severity == "high"


def test_reputation_score_targeted_highest():
    A = _load()
    a = A(mode="airgapped")
    targeted = a.normalize(a.check_ip("203.0.113.200"))
    noise = a.normalize(a.check_ip("198.51.100.2"))
    assert targeted.reputation_score > noise.reputation_score


def test_is_noise_shortcut():
    A = _load()
    assert A(mode="airgapped").is_noise("198.51.100.1") is True


def test_is_riot_shortcut():
    A = _load()
    assert A(mode="airgapped").is_riot("8.8.8.8") is True


def test_fetch_airgapped():
    A = _load()
    out = A(mode="airgapped").fetch({"type": "ip", "value": "198.51.100.2"})
    assert out.get("noise") is True
