from __future__ import annotations

import importlib


def _load_adapter():
    module = importlib.import_module("packages.integrations.navigation.tensorrt-nvidia-official.adapter")
    return module.TensorrtnvidiaOfficialAdapter


def test_manifest_metadata_is_loaded() -> None:
    adapter_cls = _load_adapter()
    manifest = adapter_cls(mode="airgapped").get_manifest()
    assert manifest.slug == "tensorrt-nvidia-official"
    assert manifest.domain == "navigation"
    assert manifest.license == "Proprietary (free fo"


def test_validate_availability_true_in_airgapped_mode() -> None:
    adapter_cls = _load_adapter()
    assert adapter_cls(mode="airgapped").validate_availability() is True


def test_execute_returns_fixture_when_airgapped() -> None:
    adapter_cls = _load_adapter()
    response = adapter_cls(mode="airgapped").execute({"operation": "engine_status"})
    assert response["source"] == "fixture"
    assert response["result"]["mission_id"] == "s3m-nav-trt-jetson-088"
