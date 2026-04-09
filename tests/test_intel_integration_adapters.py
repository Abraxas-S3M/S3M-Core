"""Unit tests for intel integration wrappers.

Military/tactical context:
These tests ensure OSINT wrappers provide deterministic behavior for sovereign,
airgapped deployments used in mission planning and intelligence briefings.
"""

from __future__ import annotations

import importlib

import pytest

from packages.integrations.base import IntegrationManifest


ADAPTER_MATRIX = [
    (
        "packages.integrations.intel.awesome-intelligence.adapter",
        "AwesomeIntelligenceAdapter",
        "awesome-intelligence",
        "Related awesome lists (e.g., arpsyndicate)",
    ),
    (
        "packages.integrations.intel.social-media-osint-tools-collection.adapter",
        "SocialMediaOsintToolsAdapter",
        "social-media-osint-tools-collection",
        "https://github.com/osintambition/Social-Media-OSINT-Tools-Collection",
    ),
    (
        "packages.integrations.intel.phoneinfoga.adapter",
        "PhoneinfogaAdapter",
        "phoneinfoga",
        "https://github.com/sundowndev/phoneinfoga",
    ),
    (
        "packages.integrations.intel.holehe.adapter",
        "HoleheAdapter",
        "holehe",
        "https://github.com/megadose/holehe",
    ),
    (
        "packages.integrations.intel.toutatis.adapter",
        "ToutatisAdapter",
        "toutatis",
        "https://github.com/megadose/toutatis",
    ),
]


@pytest.mark.parametrize(("module_path", "class_name", "slug", "source_url"), ADAPTER_MATRIX)
def test_manifest_fields_and_logger_name(
    module_path: str, class_name: str, slug: str, source_url: str
) -> None:
    module = importlib.import_module(module_path)
    adapter_cls = getattr(module, class_name)
    adapter = adapter_cls(mode="airgapped")

    manifest = adapter.get_manifest()
    assert isinstance(manifest, IntegrationManifest)
    assert manifest.slug == slug
    assert manifest.domain == "intel"
    assert manifest.source_url == source_url
    assert manifest.license == "Unknown"
    assert manifest.integration_type == "adapter"
    assert adapter.logger.name == f"s3m.integrations.intel.{slug}"


@pytest.mark.parametrize(("module_path", "class_name", "slug", "_source_url"), ADAPTER_MATRIX)
def test_execute_returns_fixture_in_airgapped_mode(
    module_path: str, class_name: str, slug: str, _source_url: str
) -> None:
    module = importlib.import_module(module_path)
    adapter_cls = getattr(module, class_name)
    adapter = adapter_cls(mode="airgapped")

    output = adapter.execute({"operation": "status"})

    assert output["integration_id"] == slug
    assert output["domain"] == "intel"
    assert output["mode"] == "airgapped"
    assert output["source"] == "fixture"
    assert output["request"] == {"operation": "status"}
    assert isinstance(output["data"], dict)
    assert output["data"].get("status") == "ok"


@pytest.mark.parametrize(("module_path", "class_name", "_slug", "_source_url"), ADAPTER_MATRIX)
def test_validate_availability_returns_bool(
    module_path: str, class_name: str, _slug: str, _source_url: str
) -> None:
    module = importlib.import_module(module_path)
    adapter_cls = getattr(module, class_name)
    adapter = adapter_cls(mode="online")

    assert isinstance(adapter.validate_availability(), bool)


@pytest.mark.parametrize(("module_path", "class_name", "_slug", "_source_url"), ADAPTER_MATRIX)
def test_execute_rejects_invalid_params(
    module_path: str, class_name: str, _slug: str, _source_url: str
) -> None:
    module = importlib.import_module(module_path)
    adapter_cls = getattr(module, class_name)
    adapter = adapter_cls(mode="airgapped")

    with pytest.raises(ValueError, match="dictionary"):
        adapter.execute(params=["invalid"])  # type: ignore[arg-type]
