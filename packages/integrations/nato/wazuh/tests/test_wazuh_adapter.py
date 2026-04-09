from __future__ import annotations

import importlib


def _load_adapter():
    module = importlib.import_module("packages.integrations.nato.wazuh.adapter")
    return module.WazuhAdapter


def test_manifest_metadata_is_loaded():
    adapter_cls = _load_adapter()
    manifest = adapter_cls(mode="airgapped").get_manifest()
    assert manifest.slug == "wazuh"
    assert manifest.domain == "nato"
    assert manifest.license == "GPL-2.0"


def test_validate_availability_true_in_airgapped_mode():
    adapter_cls = _load_adapter()
    assert adapter_cls(mode="airgapped").validate_availability() is True


def test_execute_returns_fixture_when_airgapped():
    adapter_cls = _load_adapter()
    response = adapter_cls(mode="airgapped").execute({"operation": "correlate_alerts"})
    assert response["source"] == "fixture"
    assert response["result"]["analysis_id"] == "wazuh-2026-04-09-2208"
