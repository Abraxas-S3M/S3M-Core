"""Unit tests for interop-domain integration wrappers.

Military/tactical context:
These tests verify deterministic adapter behavior for interoperability workflows
that must continue in sovereign, airgapped command environments.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path
from typing import Any

import pytest
import yaml

from packages.integrations.base import IntegrationManifest


ROOT = Path(__file__).resolve().parents[3]
INTEROP_DIR = ROOT / "packages" / "integrations" / "interop"

CASES: list[tuple[str, str, str]] = [
    (
        "open-dis-supporting-libraries",
        "OpenDisSupportingLibrariesAdapter",
        "Components within open-dis repos",
    ),
    (
        "awesome-c2-military-adaptations",
        "AwesomeC2militaryAdaptationsAdapter",
        "Search related awesome lists and forks",
    ),
]


def _load_adapter_class(slug: str, class_name: str) -> type[Any]:
    adapter_path = INTEROP_DIR / slug / "adapter.py"
    module_name = f"tests.dynamic_interop_{slug.replace('-', '_')}_adapter"
    spec = importlib.util.spec_from_file_location(module_name, adapter_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return getattr(module, class_name)


@pytest.mark.parametrize(("slug", "class_name", "expected_source_url"), CASES)
def test_manifest_fields_and_logger_name(slug: str, class_name: str, expected_source_url: str) -> None:
    adapter_cls = _load_adapter_class(slug, class_name)
    adapter = adapter_cls(mode="airgapped")
    manifest = adapter.get_manifest()

    manifest_yaml = INTEROP_DIR / slug / "manifest.yaml"
    raw = yaml.safe_load(manifest_yaml.read_text(encoding="utf-8"))

    assert isinstance(manifest, IntegrationManifest)
    assert manifest.name == raw["name"]
    assert manifest.slug == slug
    assert manifest.domain == "interop"
    assert manifest.source_url == expected_source_url
    assert manifest.license == "Unknown"
    assert manifest.integration_type == "adapter"
    assert adapter.logger.name == f"s3m.integrations.interop.{slug}"


@pytest.mark.parametrize(("slug", "class_name", "_expected_source_url"), CASES)
def test_validate_availability_in_airgapped_mode(slug: str, class_name: str, _expected_source_url: str) -> None:
    adapter_cls = _load_adapter_class(slug, class_name)
    adapter = adapter_cls(mode="airgapped")
    assert adapter.validate_availability() is True


@pytest.mark.parametrize(
    ("slug", "class_name", "_expected_source_url", "operation"),
    [
        ("open-dis-supporting-libraries", "OpenDisSupportingLibrariesAdapter", "", "coordinate_convert"),
        ("awesome-c2-military-adaptations", "AwesomeC2militaryAdaptationsAdapter", "", "catalog"),
    ],
)
def test_execute_returns_fixture_payload_in_airgapped_mode(
    slug: str, class_name: str, _expected_source_url: str, operation: str
) -> None:
    adapter_cls = _load_adapter_class(slug, class_name)
    adapter = adapter_cls(mode="airgapped")
    output = adapter.execute({"operation": operation})

    assert output["integration_id"] == slug
    assert output["domain"] == "interop"
    assert output["mode"] == "airgapped"
    assert output["source"] == "fixture"
    assert output["status"] == "ok"
    assert output["operation"] == operation
    assert isinstance(output["result"], dict)
    assert output["result"].get("status") == "ok"


@pytest.mark.parametrize(("slug", "class_name", "_expected_source_url"), CASES)
def test_validate_availability_returns_boolean_online(slug: str, class_name: str, _expected_source_url: str) -> None:
    adapter_cls = _load_adapter_class(slug, class_name)
    adapter = adapter_cls(mode="online")
    assert isinstance(adapter.validate_availability(), bool)


@pytest.mark.parametrize(("slug", "class_name", "_expected_source_url"), CASES)
def test_execute_rejects_invalid_params(slug: str, class_name: str, _expected_source_url: str) -> None:
    adapter_cls = _load_adapter_class(slug, class_name)
    adapter = adapter_cls(mode="airgapped")
    with pytest.raises(ValueError, match="dictionary"):
        adapter.execute(["invalid"])  # type: ignore[arg-type]


@pytest.mark.parametrize(("slug", "class_name", "_expected_source_url"), CASES)
def test_execute_rejects_unsupported_operation(slug: str, class_name: str, _expected_source_url: str) -> None:
    adapter_cls = _load_adapter_class(slug, class_name)
    adapter = adapter_cls(mode="airgapped")
    with pytest.raises(ValueError, match="Unsupported operation"):
        adapter.execute({"operation": "unsupported"})
