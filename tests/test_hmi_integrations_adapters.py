"""Unit tests for HMI integration adapters.

Military/tactical context:
These tests verify that HMI wrappers provide deterministic behavior in
airgapped deployments used for mission rehearsal and operator assurance.
"""

from __future__ import annotations

import importlib
from typing import Any

import pytest


CASES: list[tuple[str, str, str, str]] = [
    (
        "packages.integrations.hmi.uavs-meet-llms.adapter",
        "UavsMeetLlmsAdapter",
        "uavs-meet-llms",
        "MIT",
    ),
    ("packages.integrations.hmi.aix360.adapter", "Aix360Adapter", "aix360", "Apache 2.0"),
    ("packages.integrations.hmi.omnixai.adapter", "OmnixaiAdapter", "omnixai", "BSD-3-Clause"),
    ("packages.integrations.hmi.quantus.adapter", "QuantusAdapter", "quantus", "Apache 2.0"),
    ("packages.integrations.hmi.alibi.adapter", "AlibiAdapter", "alibi", "Apache 2.0"),
]


def _load_adapter(module_path: str, class_name: str) -> Any:
    module = importlib.import_module(module_path)
    return getattr(module, class_name)


@pytest.mark.parametrize(("module_path", "class_name", "slug", "license_name"), CASES)
def test_manifest_loading(module_path: str, class_name: str, slug: str, license_name: str) -> None:
    adapter_cls = _load_adapter(module_path, class_name)
    adapter = adapter_cls(mode="airgapped")
    manifest = adapter.get_manifest()
    assert manifest.slug == slug
    assert manifest.domain == "hmi"
    assert manifest.license == license_name
    assert manifest.name


@pytest.mark.parametrize(("module_path", "class_name", "slug", "_license_name"), CASES)
def test_validate_availability_true_in_airgapped_mode(
    module_path: str, class_name: str, slug: str, _license_name: str
) -> None:
    adapter_cls = _load_adapter(module_path, class_name)
    adapter = adapter_cls(mode="airgapped")
    result = adapter.validate_availability()
    assert isinstance(result, bool)
    assert result is True
    assert adapter.integration_id == slug


@pytest.mark.parametrize(("module_path", "class_name", "slug", "_license_name"), CASES)
def test_execute_returns_fixture_payload_in_airgapped_mode(
    module_path: str, class_name: str, slug: str, _license_name: str
) -> None:
    adapter_cls = _load_adapter(module_path, class_name)
    adapter = adapter_cls(mode="airgapped")
    payload = adapter.execute({"action": "describe"})
    assert payload["mode"] == "airgapped"
    assert payload["source"] == "fixture"
    assert payload["integration_id"] == slug
    assert payload["requested_action"] == "describe"
    assert payload["status"] == "ok"


@pytest.mark.parametrize(("module_path", "class_name", "_slug", "_license_name"), CASES)
def test_execute_rejects_non_mapping_params(
    module_path: str, class_name: str, _slug: str, _license_name: str
) -> None:
    adapter_cls = _load_adapter(module_path, class_name)
    adapter = adapter_cls(mode="airgapped")
    with pytest.raises(ValueError):
        adapter.execute(["not", "a", "mapping"])  # type: ignore[arg-type]


@pytest.mark.parametrize(("module_path", "class_name", "slug", "_license_name"), CASES)
def test_logger_name_is_consistent(module_path: str, class_name: str, slug: str, _license_name: str) -> None:
    adapter_cls = _load_adapter(module_path, class_name)
    adapter = adapter_cls(mode="airgapped")
    assert adapter.logger.name == f"s3m.integrations.hmi.{slug}"
