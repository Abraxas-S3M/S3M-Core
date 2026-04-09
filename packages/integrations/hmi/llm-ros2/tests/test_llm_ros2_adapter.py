from __future__ import annotations

import importlib


def _load_adapter():
    module = importlib.import_module("packages.integrations.hmi.llm-ros2.adapter")
    return module.LlmRos2Adapter


def test_manifest_metadata_is_loaded():
    adapter_cls = _load_adapter()
    manifest = adapter_cls(mode="airgapped").get_manifest()
    assert manifest.slug == "llm-ros2"
    assert manifest.domain == "hmi"
    assert manifest.license == "GPL-3.0"


def test_validate_availability_true_in_airgapped_mode():
    adapter_cls = _load_adapter()
    assert adapter_cls(mode="airgapped").validate_availability() is True


def test_execute_returns_fixture_when_airgapped():
    adapter_cls = _load_adapter()
    response = adapter_cls(mode="airgapped").execute({"operation": "conversation_control"})
    assert response["source"] == "fixture"
    assert response["result"]["interaction_id"] == "llmros2-op-2026-04-09-009"
