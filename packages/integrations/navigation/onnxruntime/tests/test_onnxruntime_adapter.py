from __future__ import annotations

from packages.integrations.navigation.onnxruntime.adapter import OnnxruntimeAdapter


def test_manifest_metadata_is_loaded():
    manifest = OnnxruntimeAdapter(mode="airgapped").get_manifest()
    assert manifest.slug == "onnxruntime"
    assert manifest.domain == "navigation"
    assert manifest.license == "MIT"


def test_validate_availability_true_in_airgapped_mode():
    assert OnnxruntimeAdapter(mode="airgapped").validate_availability() is True


def test_execute_returns_fixture_when_airgapped():
    response = OnnxruntimeAdapter(mode="airgapped").execute({"operation": "terrain_inference"})
    assert response["source"] == "fixture"
    assert response["result"]["event_id"] == "ort-nav-2026-04-09-001"
