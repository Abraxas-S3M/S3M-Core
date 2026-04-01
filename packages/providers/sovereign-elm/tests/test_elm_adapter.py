from __future__ import annotations

import importlib


def _load():
    adapter_mod = importlib.import_module("packages.providers.sovereign-elm.adapter")
    return adapter_mod.ElmAdapter


def test_manifest_correct():
    Adapter = _load()
    m = Adapter(mode="airgapped").get_manifest()
    assert m.tier.value == "GOVERNMENT"
    assert m.category.value == "SOVEREIGN_REGIONAL"
    assert Adapter(mode="airgapped").config.data_classification == "SAUDI_GOVERNMENT_CONFIDENTIAL"


def test_sanitize_strips_pii():
    Adapter = _load()
    data = {
        "verified": True,
        "status": "active",
        "name_ar": "REDACTED",
        "national_id": "1234567890",
        "address": "Riyadh",
        "record_type": "identity",
    }
    out = Adapter(mode="airgapped").sanitize_for_logging(data)
    assert "name_ar" not in out and "national_id" not in out and "address" not in out


def test_identity_result_no_pii_in_normalized():
    Adapter = _load()
    raw = Adapter(mode="airgapped").verify_identity("1234567890")
    out = Adapter(mode="airgapped").normalizer.normalize_identity_result(raw)
    assert "name_ar" not in out and "national_id" not in out
    assert set(out.keys()) == {"verified", "nationality", "status"}


def test_vehicle_result_no_plate():
    Adapter = _load()
    raw = Adapter(mode="airgapped").lookup_vehicle("ABC123")
    out = Adapter(mode="airgapped").normalizer.normalize_vehicle_result(raw)
    assert "plate_number" not in out and "owner_name" not in out
    assert "owner_type" in out


def test_data_classification():
    Adapter = _load()
    raw = Adapter(mode="airgapped").verify_identity("1234567890")
    assert raw["classification"] == "SAUDI_GOVERNMENT_CONFIDENTIAL"


def test_fetch_airgapped():
    Adapter = _load()
    out = Adapter(mode="airgapped").fetch({"endpoint": "identity", "national_id": "1234567890"})
    assert "verified" in out
