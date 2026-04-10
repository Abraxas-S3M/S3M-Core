from __future__ import annotations

import importlib

import pytest


CASES = [
    (
        "packages.integrations.sensor_analytics.segment-geospatial.adapter",
        "SegmentGeospatialAdapter",
        "segment-geospatial",
    ),
    (
        "packages.integrations.sensor_analytics.eo-learn.adapter",
        "EoLearnAdapter",
        "eo-learn",
    ),
    (
        "packages.integrations.sensor_analytics.awesome-geospatial.adapter",
        "AwesomeGeospatialAdapter",
        "awesome-geospatial",
    ),
    (
        "packages.integrations.sensor_analytics.awesome-gis.adapter",
        "AwesomeGisAdapter",
        "awesome-gis",
    ),
    (
        "packages.integrations.sensor_analytics.player-tool.adapter",
        "PlayerToolAdapter",
        "player-tool",
    ),
]


def _load_adapter(module_path: str, class_name: str):
    module = importlib.import_module(module_path)
    return getattr(module, class_name)


@pytest.mark.parametrize(("module_path", "class_name", "slug"), CASES)
def test_manifest_metadata_is_loaded(module_path: str, class_name: str, slug: str) -> None:
    adapter_cls = _load_adapter(module_path, class_name)
    manifest = adapter_cls(mode="airgapped").get_manifest()
    assert manifest.slug == slug
    assert manifest.domain == "sensor_analytics"
    assert manifest.license == "Unknown"


@pytest.mark.parametrize(("module_path", "class_name", "_slug"), CASES)
def test_validate_availability_true_in_airgapped_mode(
    module_path: str, class_name: str, _slug: str
) -> None:
    adapter_cls = _load_adapter(module_path, class_name)
    assert adapter_cls(mode="airgapped").validate_availability() is True


@pytest.mark.parametrize(("module_path", "class_name", "slug"), CASES)
def test_execute_returns_fixture_when_airgapped(
    module_path: str, class_name: str, slug: str
) -> None:
    adapter_cls = _load_adapter(module_path, class_name)
    response = adapter_cls(mode="airgapped").execute({"operation": "self_test"})
    assert response["source"] == "fixture"
    assert response["integration_id"] == slug
    assert response["mode"] == "airgapped"
    assert isinstance(response["result"], dict)
