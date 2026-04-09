from __future__ import annotations

import importlib


def _load_adapter():
    module = importlib.import_module("packages.integrations.nato.suricata.adapter")
    return module.SuricataAdapter


def test_manifest_metadata_is_loaded():
    adapter_cls = _load_adapter()
    manifest = adapter_cls(mode="airgapped").get_manifest()
    assert manifest.slug == "suricata"
    assert manifest.domain == "nato"
    assert manifest.license == "GPL-2.0"


def test_validate_availability_true_in_airgapped_mode():
    adapter_cls = _load_adapter()
    assert adapter_cls(mode="airgapped").validate_availability() is True


def test_execute_returns_fixture_when_airgapped():
    adapter_cls = _load_adapter()
    response = adapter_cls(mode="airgapped").execute({"operation": "analyze_pcap"})
    assert response["source"] == "fixture"
    assert response["result"]["analysis_id"] == "suri-2026-04-09-1001"
