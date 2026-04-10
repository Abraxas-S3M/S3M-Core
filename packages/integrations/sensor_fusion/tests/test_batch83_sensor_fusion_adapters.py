from __future__ import annotations

import importlib

import pytest


CASES = [
    (
        "packages.integrations.sensor_fusion.m3dgr.adapter",
        "M3dgrAdapter",
        "m3dgr",
        "MIT",
        "m3dgr-sf-2026-04-10-001",
    ),
    (
        "packages.integrations.sensor_fusion.liv-handhold-2.adapter",
        "LivHandhold2Adapter",
        "liv-handhold-2",
        "MIT",
        "liv-handhold-2-sf-2026-04-10-001",
    ),
    (
        "packages.integrations.sensor_fusion.awesome-radar-perception.adapter",
        "AwesomeRadarPerceptionAdapter",
        "awesome-radar-perception",
        "MIT",
        "awesome-radar-perception-sf-2026-04-10-001",
    ),
]


def _load_adapter(module_path: str, class_name: str):
    module = importlib.import_module(module_path)
    return getattr(module, class_name)


@pytest.mark.parametrize(("module_path", "class_name", "slug", "license_name", "_event_id"), CASES)
def test_manifest_metadata_is_loaded(
    module_path: str,
    class_name: str,
    slug: str,
    license_name: str,
    _event_id: str,
) -> None:
    adapter_cls = _load_adapter(module_path, class_name)
    manifest = adapter_cls(mode="airgapped").get_manifest()
    assert manifest.slug == slug
    assert manifest.domain == "sensor_fusion"
    assert manifest.license == license_name


@pytest.mark.parametrize(("module_path", "class_name", "_slug", "_license_name", "_event_id"), CASES)
def test_validate_availability_true_in_airgapped_mode(
    module_path: str,
    class_name: str,
    _slug: str,
    _license_name: str,
    _event_id: str,
) -> None:
    adapter_cls = _load_adapter(module_path, class_name)
    assert adapter_cls(mode="airgapped").validate_availability() is True


@pytest.mark.parametrize(("module_path", "class_name", "slug", "_license_name", "event_id"), CASES)
def test_execute_returns_fixture_when_airgapped(
    module_path: str,
    class_name: str,
    slug: str,
    _license_name: str,
    event_id: str,
) -> None:
    adapter_cls = _load_adapter(module_path, class_name)
    response = adapter_cls(mode="airgapped").execute({"operation": "self_test"})
    assert response["source"] == "fixture"
    assert response["integration_id"] == slug
    assert response["mode"] == "airgapped"
    assert response["result"]["event_id"] == event_id


@pytest.mark.parametrize(("module_path", "class_name", "_slug", "_license_name", "_event_id"), CASES)
def test_execute_rejects_non_mapping_params(
    module_path: str,
    class_name: str,
    _slug: str,
    _license_name: str,
    _event_id: str,
) -> None:
    adapter_cls = _load_adapter(module_path, class_name)
    with pytest.raises(ValueError, match="params must be a dictionary"):
        adapter_cls(mode="airgapped").execute(["invalid"])  # type: ignore[arg-type]
