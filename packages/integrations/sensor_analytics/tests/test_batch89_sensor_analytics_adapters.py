from __future__ import annotations

import importlib

import pytest


CASES = [
    (
        "packages.integrations.sensor_analytics.military-tools-geoprocessing-toolbox.adapter",
        "MilitaryToolsGeoprocessingToolboxAdapter",
        "military-tools-geoprocessing-toolbox",
        "mtgt-sa-2026-04-10-001",
    ),
    (
        "packages.integrations.sensor_analytics.samgeo-segment-geospatial-extensions.adapter",
        "SamgeosegmentGeospatialExtensionsAdapter",
        "samgeo-segment-geospatial-extensions",
        "samgeo-sa-2026-04-10-002",
    ),
    (
        "packages.integrations.sensor_analytics.geotracknet-extensions.adapter",
        "GeotracknetExtensionsAdapter",
        "geotracknet-extensions",
        "gtn-sa-2026-04-10-003",
    ),
    (
        "packages.integrations.sensor_analytics.debasis-dotcom-ship-detection-from-satel.adapter",
        "DebasisDotcomshipDetectionFromAdapter",
        "debasis-dotcom-ship-detection-from-satel",
        "yolov4-ship-sa-2026-04-10-004",
    ),
    (
        "packages.integrations.sensor_analytics.awesome-remote-sensing.adapter",
        "AwesomeRemoteSensingAdapter",
        "awesome-remote-sensing",
        "ars-sa-2026-04-10-005",
    ),
]


def _load_adapter(module_path: str, class_name: str):
    module = importlib.import_module(module_path)
    return getattr(module, class_name)


@pytest.mark.parametrize(("module_path", "class_name", "slug", "_event_id"), CASES)
def test_manifest_metadata_is_loaded(
    module_path: str, class_name: str, slug: str, _event_id: str
) -> None:
    adapter_cls = _load_adapter(module_path, class_name)
    manifest = adapter_cls(mode="airgapped").get_manifest()
    assert manifest.slug == slug
    assert manifest.domain == "sensor_analytics"
    assert manifest.license == "Unknown"


@pytest.mark.parametrize(("module_path", "class_name", "_slug", "_event_id"), CASES)
def test_validate_availability_true_in_airgapped_mode(
    module_path: str, class_name: str, _slug: str, _event_id: str
) -> None:
    adapter_cls = _load_adapter(module_path, class_name)
    assert adapter_cls(mode="airgapped").validate_availability() is True


@pytest.mark.parametrize(("module_path", "class_name", "slug", "event_id"), CASES)
def test_execute_returns_fixture_when_airgapped(
    module_path: str, class_name: str, slug: str, event_id: str
) -> None:
    adapter_cls = _load_adapter(module_path, class_name)
    response = adapter_cls(mode="airgapped").execute({"operation": "self_test"})
    assert response["source"] == "fixture"
    assert response["integration_id"] == slug
    assert response["mode"] == "airgapped"
    assert response["result"]["event_id"] == event_id
