from __future__ import annotations

import importlib

import pytest


CASES = [
    (
        "packages.integrations.sensor_fusion.military-target-and-equipment-detection.adapter",
        "MilitaryTargetAndEquipmentAdapter",
        "military-target-and-equipment-detection",
        "MIT",
        "mission_id",
    ),
    (
        "packages.integrations.sensor_fusion.automatic-target-recognition-using-sar-i.adapter",
        "AutomaticTargetRecognitionUsingAdapter",
        "automatic-target-recognition-using-sar-i",
        "MIT",
        "mission_id",
    ),
    (
        "packages.integrations.sensor_fusion.military-yolov5.adapter",
        "MilitaryYolov5Adapter",
        "military-yolov5",
        "MIT",
        "mission_id",
    ),
    (
        "packages.integrations.sensor_fusion.uav-tracking-tank.adapter",
        "UavTrackingTankAdapter",
        "uav-tracking-tank",
        "MIT",
        "mission_id",
    ),
    (
        "packages.integrations.sensor_fusion.aircraftdetectionyolov5.adapter",
        "Aircraftdetectionyolov5Adapter",
        "aircraftdetectionyolov5",
        "MIT",
        "mission_id",
    ),
]


def _load_adapter(module_path: str, class_name: str):
    module = importlib.import_module(module_path)
    return getattr(module, class_name)


@pytest.mark.parametrize(("module_path", "class_name", "slug", "license_name", "fixture_key"), CASES)
def test_manifest_metadata_is_loaded(
    module_path: str,
    class_name: str,
    slug: str,
    license_name: str,
    fixture_key: str,
) -> None:
    del fixture_key
    adapter_cls = _load_adapter(module_path, class_name)
    manifest = adapter_cls(mode="airgapped").get_manifest()
    assert manifest.slug == slug
    assert manifest.domain == "sensor_fusion"
    assert manifest.license == license_name


@pytest.mark.parametrize(("module_path", "class_name", "_slug", "_license_name", "_fixture_key"), CASES)
def test_validate_availability_true_in_airgapped_mode(
    module_path: str,
    class_name: str,
    _slug: str,
    _license_name: str,
    _fixture_key: str,
) -> None:
    adapter_cls = _load_adapter(module_path, class_name)
    assert adapter_cls(mode="airgapped").validate_availability() is True


@pytest.mark.parametrize(("module_path", "class_name", "slug", "_license_name", "fixture_key"), CASES)
def test_execute_returns_fixture_when_airgapped(
    module_path: str,
    class_name: str,
    slug: str,
    _license_name: str,
    fixture_key: str,
) -> None:
    adapter_cls = _load_adapter(module_path, class_name)
    response = adapter_cls(mode="airgapped").execute({"operation": "self_test"})
    assert response["source"] == "fixture"
    assert response["integration_id"] == slug
    assert response["mode"] == "airgapped"
    assert isinstance(response["result"], dict)
    assert fixture_key in response["result"]
