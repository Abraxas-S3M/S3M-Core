"""Tests for dashboard integration wrappers in sovereign airgapped workflows."""

from __future__ import annotations

import importlib
from typing import Any

import pytest


CASES = [
    (
        "packages.integrations.dashboard.awesome-asset-discovery-curated.adapter",
        "AwesomeAssetDiscoverycuratedAdapter",
        "awesome-asset-discovery-curated",
        "MIT",
    ),
    (
        "packages.integrations.dashboard.actual.adapter",
        "ActualAdapter",
        "actual",
        "MIT",
    ),
    (
        "packages.integrations.dashboard.ocular.adapter",
        "OcularAdapter",
        "ocular",
        "MIT",
    ),
    (
        "packages.integrations.dashboard.erpnext.adapter",
        "ErpnextAdapter",
        "erpnext",
        "GPL-3.0",
    ),
    (
        "packages.integrations.dashboard.ghosts.adapter",
        "GhostsAdapter",
        "ghosts",
        "Apache 2.0",
    ),
]


def _load_adapter(module_path: str, class_name: str) -> type[Any]:
    module = importlib.import_module(module_path)
    return getattr(module, class_name)


@pytest.mark.parametrize(("module_path", "class_name", "slug", "license_name"), CASES)
def test_manifest_and_logger_shape(module_path: str, class_name: str, slug: str, license_name: str) -> None:
    adapter_cls = _load_adapter(module_path, class_name)
    adapter = adapter_cls(mode="airgapped")

    manifest = adapter.get_manifest()
    assert manifest.slug == slug
    assert manifest.domain == "dashboard"
    assert manifest.license == license_name
    assert manifest.airgapped_support is True
    assert adapter.logger.name == f"s3m.integrations.dashboard.{slug}"


@pytest.mark.parametrize(("module_path", "class_name", "slug", "_license_name"), CASES)
def test_execute_airgapped_returns_fixture_data(
    module_path: str,
    class_name: str,
    slug: str,
    _license_name: str,
) -> None:
    adapter_cls = _load_adapter(module_path, class_name)
    adapter = adapter_cls(mode="airgapped")

    result = adapter.execute({"action": "status"})
    assert result["integration_id"] == slug
    assert result["mode"] == "airgapped"
    assert result["source"] == "fixture"
    assert isinstance(result["data"], dict)
    assert result["data"] != {}


@pytest.mark.parametrize(("module_path", "class_name", "_slug", "_license_name"), CASES)
def test_execute_rejects_invalid_action(
    module_path: str,
    class_name: str,
    _slug: str,
    _license_name: str,
) -> None:
    adapter_cls = _load_adapter(module_path, class_name)
    adapter = adapter_cls(mode="airgapped")

    with pytest.raises(ValueError):
        adapter.execute({"action": ""})

    with pytest.raises(TypeError):
        adapter.execute(params="invalid")  # type: ignore[arg-type]
