from __future__ import annotations

import importlib


def _load_adapter():
    module = importlib.import_module("packages.integrations.sensor_fusion.ultralytics-yolov8-yolo11.adapter")
    return module.Ultralyticsyolov8yolo11Adapter


def test_manifest_metadata_is_loaded() -> None:
    adapter_cls = _load_adapter()
    manifest = adapter_cls(mode="airgapped").get_manifest()
    assert manifest.slug == "ultralytics-yolov8-yolo11"
    assert manifest.domain == "sensor_fusion"
    assert manifest.license == "AGPL-3.0"


def test_validate_availability_true_in_airgapped_mode() -> None:
    adapter_cls = _load_adapter()
    assert adapter_cls(mode="airgapped").validate_availability() is True


def test_execute_returns_fixture_when_airgapped() -> None:
    adapter_cls = _load_adapter()
    response = adapter_cls(mode="airgapped").execute({"operation": "real_time_threat_screening"})
    assert response["source"] == "fixture"
    assert response["result"]["snapshot_id"] == "ultralytics-s3m-2026-04-10T121000Z"
