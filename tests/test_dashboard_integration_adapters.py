"""Unit tests for dashboard-domain integration wrappers."""

from __future__ import annotations

import importlib

import pytest

from packages.integrations.base import IntegrationManifest


ADAPTER_CASES = [
    ("opencti", "OpenctiAdapter", "OpenCTI", "Apache 2.0"),
    ("jsbsim", "JsbsimAdapter", "JSBSim", "LGPL-2.1"),
    ("langfuse", "LangfuseAdapter", "Langfuse", "MIT"),
    ("evidently", "EvidentlyAdapter", "Evidently", "Apache 2.0"),
    ("phoenix", "PhoenixAdapter", "Phoenix", "Apache 2.0"),
]


def _load_adapter(slug: str, class_name: str):
    module = importlib.import_module(f"packages.integrations.dashboard.{slug}.adapter")
    return getattr(module, class_name)


@pytest.mark.parametrize("slug,class_name,expected_name,expected_license", ADAPTER_CASES)
def test_manifest_metadata_is_loaded_from_yaml(
    slug: str,
    class_name: str,
    expected_name: str,
    expected_license: str,
) -> None:
    adapter_cls = _load_adapter(slug, class_name)
    adapter = adapter_cls(mode="airgapped")
    manifest = adapter.get_manifest()

    assert isinstance(manifest, IntegrationManifest)
    assert manifest.name == expected_name
    assert manifest.slug == slug
    assert manifest.domain == "dashboard"
    assert manifest.license == expected_license
    assert manifest.source_url.startswith("https://github.com/")
    assert manifest.integration_type == "adapter"
    assert manifest.airgapped_support is True


@pytest.mark.parametrize("slug,class_name,_,__", ADAPTER_CASES)
def test_validate_availability_true_in_airgapped_mode(slug: str, class_name: str, _: str, __: str) -> None:
    adapter_cls = _load_adapter(slug, class_name)
    adapter = adapter_cls(mode="airgapped")
    assert adapter.validate_availability() is True


@pytest.mark.parametrize("slug,class_name,_,__", ADAPTER_CASES)
def test_execute_returns_fixture_payload_in_airgapped_mode(slug: str, class_name: str, _: str, __: str) -> None:
    adapter_cls = _load_adapter(slug, class_name)
    adapter = adapter_cls(mode="airgapped")
    result = adapter.execute({"action": "dashboard_summary"})

    assert result["integration_id"] == slug
    assert result["domain"] == "dashboard"
    assert result["mode"] == "airgapped"
    assert result["source"] == "fixture"
    assert result["action"] == "dashboard_summary"
    assert isinstance(result["result"], dict)
    assert result["result"]


@pytest.mark.parametrize("slug,class_name,_,__", ADAPTER_CASES)
def test_execute_rejects_non_mapping_input(slug: str, class_name: str, _: str, __: str) -> None:
    adapter_cls = _load_adapter(slug, class_name)
    adapter = adapter_cls(mode="airgapped")
    with pytest.raises(ValueError, match="params must be a mapping"):
        adapter.execute("invalid-input")  # type: ignore[arg-type]

