from __future__ import annotations

import importlib

import pytest


CASES = [
    (
        "packages.integrations.sensor_fusion.particle-filter.adapter",
        "ParticleFilterAdapter",
        "particle-filter",
        "MIT",
    ),
    (
        "packages.integrations.sensor_fusion.ros-sensor-fusion-tutorial.adapter",
        "RosSensorFusionTutorialAdapter",
        "ros-sensor-fusion-tutorial",
        "MIT",
    ),
    (
        "packages.integrations.sensor_fusion.m2s2.adapter",
        "M2s2Adapter",
        "m2s2",
        "MIT",
    ),
    (
        "packages.integrations.sensor_fusion.sensor-fusion.adapter",
        "SensorFusionAdapter",
        "sensor-fusion",
        "MIT",
    ),
    (
        "packages.integrations.sensor_fusion.lidar-radar-fusion-ekf-ukf.adapter",
        "LidarRadarFusionEkfAdapter",
        "lidar-radar-fusion-ekf-ukf",
        "MIT",
    ),
]


def _load_adapter(module_path: str, class_name: str):
    module = importlib.import_module(module_path)
    return getattr(module, class_name)


@pytest.mark.parametrize(("module_path", "class_name", "slug", "license_name"), CASES)
def test_manifest_metadata_is_loaded(
    module_path: str, class_name: str, slug: str, license_name: str
) -> None:
    adapter_cls = _load_adapter(module_path, class_name)
    manifest = adapter_cls(mode="airgapped").get_manifest()
    assert manifest.slug == slug
    assert manifest.domain == "sensor_fusion"
    assert manifest.license == license_name


@pytest.mark.parametrize(("module_path", "class_name", "_slug", "_license_name"), CASES)
def test_validate_availability_true_in_airgapped_mode(
    module_path: str, class_name: str, _slug: str, _license_name: str
) -> None:
    adapter_cls = _load_adapter(module_path, class_name)
    assert adapter_cls(mode="airgapped").validate_availability() is True


@pytest.mark.parametrize(("module_path", "class_name", "slug", "_license_name"), CASES)
def test_execute_returns_fixture_when_airgapped(
    module_path: str, class_name: str, slug: str, _license_name: str
) -> None:
    adapter_cls = _load_adapter(module_path, class_name)
    response = adapter_cls(mode="airgapped").execute({"operation": "self_test"})
    assert response["source"] == "fixture"
    assert response["integration_id"] == slug
    assert response["mode"] == "airgapped"
    assert isinstance(response["result"], dict)
