from __future__ import annotations

import importlib

import pytest


CASES = [
    (
        "packages.integrations.sensor_analytics.geotracknet.adapter",
        "GeotracknetAdapter",
        "geotracknet",
        "Unknown",
    ),
    (
        "packages.integrations.sensor_analytics.sarfish.adapter",
        "SarfishAdapter",
        "sarfish",
        "Unknown",
    ),
    (
        "packages.integrations.sensor_analytics.sarmssd.adapter",
        "SarmssdAdapter",
        "sarmssd",
        "Unknown",
    ),
    (
        "packages.integrations.sensor_analytics.speckle2void.adapter",
        "Speckle2voidAdapter",
        "speckle2void",
        "Unknown",
    ),
    (
        "packages.integrations.sensor_analytics.geoai.adapter",
        "GeoaiAdapter",
        "geoai",
        "Unknown",
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
    assert manifest.domain == "sensor_analytics"
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


@pytest.mark.parametrize(("module_path", "class_name", "_slug", "_license_name"), CASES)
def test_execute_rejects_non_dict_params(
    module_path: str, class_name: str, _slug: str, _license_name: str
) -> None:
    adapter_cls = _load_adapter(module_path, class_name)
    with pytest.raises(ValueError):
        adapter_cls(mode="airgapped").execute("invalid")  # type: ignore[arg-type]
