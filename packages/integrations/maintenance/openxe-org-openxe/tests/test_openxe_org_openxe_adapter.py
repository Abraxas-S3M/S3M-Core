from __future__ import annotations

import importlib


def _load_adapter():
    module = importlib.import_module("packages.integrations.maintenance.openxe-org-openxe.adapter")
    return module.OpenxeOrgopenxeAdapter


def test_manifest_metadata_is_loaded():
    adapter_cls = _load_adapter()
    manifest = adapter_cls(mode="airgapped").get_manifest()
    assert manifest.slug == "openxe-org-openxe"
    assert manifest.domain == "maintenance"
    assert manifest.license == "Unknown"


def test_validate_availability_true_in_airgapped_mode():
    adapter_cls = _load_adapter()
    assert adapter_cls(mode="airgapped").validate_availability() is True


def test_execute_returns_fixture_when_airgapped():
    adapter_cls = _load_adapter()
    response = adapter_cls(mode="airgapped").execute({"operation": "maintenance_procurement_alignment"})
    assert response["source"] == "fixture"
    assert response["result"]["snapshot_id"] == "openxe-maint-2026-0410-1200z"
