from __future__ import annotations

import importlib

import pytest


def _load_adapter():
    module = importlib.import_module("packages.integrations.nato.detectron2-object-detection.adapter")
    return module.Detectron2objectDetectionAdapter


def test_manifest_metadata_is_loaded():
    adapter_cls = _load_adapter()
    manifest = adapter_cls(mode="airgapped").get_manifest()
    assert manifest.slug == "detectron2-object-detection"
    assert manifest.domain == "nato"
    assert manifest.license == "Apache-2.0"


def test_validate_availability_true_in_airgapped_mode():
    adapter_cls = _load_adapter()
    assert adapter_cls(mode="airgapped").validate_availability() is True


def test_execute_returns_fixture_when_airgapped():
    adapter_cls = _load_adapter()
    response = adapter_cls(mode="airgapped").execute({"operation": "object_detection"})
    assert response["source"] == "fixture"
    assert response["result"]["detections"][0]["label"] == "armored_vehicle"


def test_logger_name_uses_required_nato_prefix():
    adapter_cls = _load_adapter()
    adapter = adapter_cls(mode="airgapped")
    assert adapter.logger.name == "s3m.integrations.nato.detectron2-object-detection"


def test_execute_rejects_unsupported_operation():
    adapter_cls = _load_adapter()
    adapter = adapter_cls(mode="airgapped")
    with pytest.raises(ValueError, match="Unsupported operation"):
        adapter.execute({"operation": "freeform_detection"})
