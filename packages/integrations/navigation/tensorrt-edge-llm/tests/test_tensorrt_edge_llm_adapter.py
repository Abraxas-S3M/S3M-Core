from __future__ import annotations

import importlib


def _load_adapter():
    module = importlib.import_module("packages.integrations.navigation.tensorrt-edge-llm.adapter")
    return module.TensorrtEdgeLlmAdapter


def test_manifest_metadata_is_loaded():
    adapter_cls = _load_adapter()
    manifest = adapter_cls(mode="airgapped").get_manifest()
    assert manifest.slug == "tensorrt-edge-llm"
    assert manifest.domain == "navigation"
    assert manifest.license == "(NVIDIA)"


def test_validate_availability_true_in_airgapped_mode():
    adapter_cls = _load_adapter()
    assert adapter_cls(mode="airgapped").validate_availability() is True


def test_execute_returns_fixture_when_airgapped():
    adapter_cls = _load_adapter()
    response = adapter_cls(mode="airgapped").execute({"operation": "edge_llm_inference"})
    assert response["source"] == "fixture"
    assert response["result"]["event_id"] == "trt-edge-llm-nav-2026-04-09-021"
