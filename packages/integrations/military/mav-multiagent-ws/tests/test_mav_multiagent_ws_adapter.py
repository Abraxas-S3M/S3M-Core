from __future__ import annotations

import importlib


def _load_adapter():
    module = importlib.import_module("packages.integrations.military.mav-multiagent-ws.adapter")
    return module.MavMultiagentWsAdapter


def test_manifest_metadata_is_loaded() -> None:
    adapter_cls = _load_adapter()
    manifest = adapter_cls(mode="airgapped").get_manifest()
    assert manifest.slug == "mav-multiagent-ws"
    assert manifest.domain == "military"
    assert manifest.license == "(BSD-style)"


def test_validate_availability_true_in_airgapped_mode() -> None:
    adapter_cls = _load_adapter()
    assert adapter_cls(mode="airgapped").validate_availability() is True


def test_execute_returns_fixture_when_airgapped() -> None:
    adapter_cls = _load_adapter()
    response = adapter_cls(mode="airgapped").execute({"operation": "coordinate_multi_uav"})
    assert response["source"] == "fixture"
    assert response["result"]["coordination_id"] == "mav-maws-2026-04-09-003"
