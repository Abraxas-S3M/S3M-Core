from __future__ import annotations

import importlib


def _load():
    adapter_mod = importlib.import_module("packages.providers.sovereign-saudi-nca.adapter")
    norm_mod = importlib.import_module("packages.providers.sovereign-saudi-nca.normalizer")
    cfg_mod = importlib.import_module("packages.providers.sovereign-saudi-nca.config")
    return adapter_mod.SaudiNCAAdapter, norm_mod.SaudiNCANormalizer, cfg_mod


def test_manifest_correct():
    Adapter, _, _ = _load()
    m = Adapter(mode="airgapped").get_manifest()
    assert m.tier.value == "GOVERNMENT"
    assert m.category.value == "SOVEREIGN_REGIONAL"


def test_advisories_bilingual():
    Adapter, _, _ = _load()
    advisories = Adapter(mode="airgapped").get_advisories()["advisories"]
    for a in advisories:
        assert a["title_ar"] and a["title_en"] and a["description_ar"] and a["description_en"]


def test_advisory_has_sectors():
    Adapter, _, _ = _load()
    adv = Adapter(mode="airgapped").get_advisories()["advisories"][0]
    assert len(adv["affected_sectors"]) >= 1


def test_normalize_advisory_to_threat_indicators():
    Adapter, Normalizer, _ = _load()
    advisory = Adapter(mode="airgapped").get_advisories()["advisories"][0]
    out = Normalizer().normalize_advisory(advisory)
    assert len(out) == 5


def test_normalize_confidence_government():
    Adapter, Normalizer, _ = _load()
    advisory = Adapter(mode="airgapped").get_advisories()["advisories"][0]
    out = Normalizer().normalize_advisory(advisory)[0]
    assert out.confidence == 0.95


def test_vulnerability_saudi_exploitation_flag():
    Adapter, _, _ = _load()
    vulns = Adapter(mode="airgapped").get_vulnerability_alerts()["vulnerabilities"]
    assert any(v.get("saudi_exploitation_confirmed") for v in vulns)


def test_compliance_ccc_controls():
    Adapter, _, _ = _load()
    ccc = Adapter(mode="airgapped").get_compliance_status("CCC")
    assert len(ccc["controls"]) == 10
    assert "s3m_compliance_mapping" in ccc


def test_ioc_feed_types():
    Adapter, _, _ = _load()
    iocs = Adapter(mode="airgapped").get_ioc_feed(confidence="high")["iocs"]
    types = {i["type"] for i in iocs}
    assert {"ip", "domain", "hash", "url", "cve"}.issubset(types)


def test_feed_to_soc_bridge():
    Adapter, _, _ = _load()
    advisories = Adapter(mode="airgapped").get_advisories()["advisories"]
    out = Adapter(mode="airgapped").feed_to_soc(advisories)
    assert out["critical_count"] >= 1


def test_works_without_gov_api():
    Adapter, _, _ = _load()
    assert Adapter(mode="airgapped").validate_credentials() is True


def test_fetch_airgapped():
    Adapter, _, _ = _load()
    out = Adapter(mode="airgapped").fetch({"endpoint": "advisories"})
    assert out["count"] >= 1
