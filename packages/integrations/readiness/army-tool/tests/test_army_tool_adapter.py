from __future__ import annotations

import importlib


def _load_adapter():
    module = importlib.import_module("packages.integrations.readiness.army-tool.adapter")
    return module.ArmyToolAdapter


def test_manifest_metadata_is_loaded():
    adapter_cls = _load_adapter()
    manifest = adapter_cls(mode="airgapped").get_manifest()
    assert manifest.slug == "army-tool"
    assert manifest.domain == "readiness"
    assert manifest.license == "Unknown"


def test_validate_availability_true_in_airgapped_mode():
    adapter_cls = _load_adapter()
    assert adapter_cls(mode="airgapped").validate_availability() is True


def test_execute_returns_fixture_when_airgapped():
    adapter_cls = _load_adapter()
    response = adapter_cls(mode="airgapped").execute({"operation": "readiness_snapshot"})
    assert response["source"] == "fixture"
    assert response["result"]["report_id"] == "at-readiness-2026-04-10-01"
