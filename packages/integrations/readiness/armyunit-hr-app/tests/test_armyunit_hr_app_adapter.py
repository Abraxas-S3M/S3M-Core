from __future__ import annotations

import importlib


def _load_adapter():
    module = importlib.import_module("packages.integrations.readiness.armyunit-hr-app.adapter")
    return module.ArmyunitHrAppAdapter


def test_manifest_metadata_is_loaded():
    adapter_cls = _load_adapter()
    manifest = adapter_cls(mode="airgapped").get_manifest()
    assert manifest.slug == "armyunit-hr-app"
    assert manifest.domain == "readiness"
    assert manifest.license == "Unknown"


def test_validate_availability_true_in_airgapped_mode():
    adapter_cls = _load_adapter()
    assert adapter_cls(mode="airgapped").validate_availability() is True


def test_execute_returns_fixture_when_airgapped():
    adapter_cls = _load_adapter()
    response = adapter_cls(mode="airgapped").execute({"operation": "staff_readiness_report"})
    assert response["source"] == "fixture"
    assert response["result"]["report_id"] == "auhr-readiness-2026-04-10-01"
