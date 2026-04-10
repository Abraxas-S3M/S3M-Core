from __future__ import annotations

import importlib


def _load_adapter():
    module = importlib.import_module("packages.integrations.swarm.uav-orchestrator.adapter")
    return module.UavOrchestratorAdapter


def test_manifest_metadata_is_loaded() -> None:
    adapter_cls = _load_adapter()
    manifest = adapter_cls(mode="airgapped").get_manifest()
    assert manifest.slug == "uav-orchestrator"
    assert manifest.domain == "swarm"
    assert manifest.license == "MIT"


def test_validate_availability_true_in_airgapped_mode() -> None:
    adapter_cls = _load_adapter()
    assert adapter_cls(mode="airgapped").validate_availability() is True


def test_execute_returns_fixture_when_airgapped() -> None:
    adapter_cls = _load_adapter()
    response = adapter_cls(mode="airgapped").execute({"operation": "orchestrate_uav_swarm"})
    assert response["source"] == "fixture"
    assert response["result"]["sortie_id"] == "uav-orch-sierra-2026-04-10-004"

