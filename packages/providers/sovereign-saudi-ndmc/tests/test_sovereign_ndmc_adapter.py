from __future__ import annotations

import importlib


def _load():
    adapter_mod = importlib.import_module("packages.providers.sovereign-saudi-ndmc.adapter")
    cfg_mod = importlib.import_module("packages.providers.sovereign-saudi-ndmc.config")
    return adapter_mod.SovereignNDMCAdapter, cfg_mod


def test_manifest_correct():
    Adapter, _ = _load()
    m = Adapter(mode="airgapped").get_manifest()
    assert m.tier.value == "GOVERNMENT"
    assert m.category.value == "SOVEREIGN_REGIONAL"
    assert m.auth_type == "certificate"


def test_data_classification_enforced():
    Adapter, _ = _load()
    alerts = Adapter(mode="airgapped").get_official_alerts()["alerts"]
    assert all(a["classification"] == "SAUDI_GOVERNMENT_OFFICIAL" for a in alerts)


def test_arabic_primary_language():
    Adapter, _ = _load()
    alerts = Adapter(mode="airgapped").get_official_alerts()["alerts"]
    assert all(bool(a.get("alert_ar", "").strip()) for a in alerts)


def test_data_sharing_agreement_defined():
    _, cfg_mod = _load()
    agreement = cfg_mod.DATA_SHARING_AGREEMENT
    for key in ["authority", "ministry", "data_types", "classification"]:
        assert key in agreement


def test_military_advisory_has_ops_impact():
    Adapter, _ = _load()
    impact = Adapter(mode="airgapped").get_military_weather_advisory()["advisory"]["operational_impact"]
    assert {"flight", "ground", "uav", "maritime"}.issubset(impact.keys())


def test_military_advisory_bilingual():
    Adapter, _ = _load()
    advisory = Adapter(mode="airgapped").get_military_weather_advisory()["advisory"]
    assert advisory["conditions_ar"] and advisory["conditions_en"]


def test_sovereign_alert_types_defined():
    Adapter, _ = _load()
    assert len(Adapter(mode="airgapped").config.sovereign_alert_types) == 8


def test_works_without_gov_api():
    Adapter, _ = _load()
    assert Adapter(mode="airgapped").validate_credentials() is True


def test_data_sharing_sla_status():
    Adapter, _ = _load()
    status = Adapter(mode="airgapped").get_data_sharing_status()["sla_status"]
    assert status in {"compliant", "degraded", "non_compliant"}


def test_fetch_airgapped():
    Adapter, _ = _load()
    out = Adapter(mode="airgapped").fetch({"endpoint": "official_alerts"})
    assert len(out["alerts"]) >= 1
