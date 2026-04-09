"""Unit tests for Human-Machine Teaming integration wrappers.

Military/tactical context:
These tests ensure sovereign HMI adapters behave deterministically in airgapped
operations where mission teams need dependable observability and explainability.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path
from typing import Any, Type

import pytest

from packages.integrations.base import IntegrationAdapter
from packages.integrations.registry import discover_integration_manifests


REPO_ROOT = Path(__file__).resolve().parents[1]

ADAPTER_MATRIX: list[dict[str, str]] = [
    {
        "slug": "langfuse",
        "class_name": "LangfuseAdapter",
        "source_url": "https://github.com/langfuse/langfuse",
        "license": "MIT",
        "operation": "trace_summary",
    },
    {
        "slug": "phoenix",
        "class_name": "PhoenixAdapter",
        "source_url": "https://github.com/arize-ai/phoenix",
        "license": "Apache 2.0",
        "operation": "experiment_summary",
    },
    {
        "slug": "explainerdashboard",
        "class_name": "ExplainerdashboardAdapter",
        "source_url": "https://github.com/oegedijk/explainerdashboard",
        "license": "MIT",
        "operation": "feature_impact",
    },
    {
        "slug": "modelstudio",
        "class_name": "ModelstudioAdapter",
        "source_url": "https://github.com/ModelOriented/modelStudio",
        "license": "GPL-3.0",
        "operation": "model_exploration",
    },
    {
        "slug": "grafana-with-llm-plugins",
        "class_name": "GrafanawithLlmPluginsAdapter",
        "source_url": "https://github.com/grafana/grafana",
        "license": "AGPL-3.0",
        "operation": "dashboard_status",
    },
]


def _load_adapter_class(slug: str, class_name: str) -> Type[IntegrationAdapter]:
    adapter_path = REPO_ROOT / "packages" / "integrations" / "hmi" / slug / "adapter.py"
    module_name = f"packages.integrations.hmi.{slug.replace('-', '_')}.adapter"
    spec = importlib.util.spec_from_file_location(module_name, adapter_path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Unable to load adapter module for slug={slug}")

    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    adapter_cls = getattr(module, class_name)
    if not issubclass(adapter_cls, IntegrationAdapter):
        raise TypeError(f"{class_name} is not an IntegrationAdapter subclass")
    return adapter_cls


@pytest.mark.parametrize("entry", ADAPTER_MATRIX)
def test_manifest_fields_and_logger_name(entry: dict[str, Any]) -> None:
    adapter_cls = _load_adapter_class(entry["slug"], entry["class_name"])
    adapter = adapter_cls(mode="airgapped")
    manifest = adapter.get_manifest()

    assert manifest.slug == entry["slug"]
    assert manifest.domain == "hmi"
    assert manifest.source_url == entry["source_url"]
    assert manifest.license == entry["license"]
    assert manifest.integration_type == "adapter"
    assert adapter.logger.name == f"s3m.integrations.hmi.{entry['slug']}"


@pytest.mark.parametrize("entry", ADAPTER_MATRIX)
def test_execute_airgapped_returns_fixture_payload(entry: dict[str, Any]) -> None:
    adapter_cls = _load_adapter_class(entry["slug"], entry["class_name"])
    output = adapter_cls(mode="airgapped").execute({"operation": entry["operation"]})

    assert output["integration_id"] == entry["slug"]
    assert output["domain"] == "hmi"
    assert output["mode"] == "airgapped"
    assert output["source"] == "fixture"
    assert output["operation"] == entry["operation"]
    assert isinstance(output["data"], dict)
    assert output["data"].get("status") == "ok"


@pytest.mark.parametrize("entry", ADAPTER_MATRIX)
def test_validate_availability_returns_bool(entry: dict[str, Any]) -> None:
    adapter_cls = _load_adapter_class(entry["slug"], entry["class_name"])
    assert isinstance(adapter_cls(mode="online").validate_availability(), bool)


@pytest.mark.parametrize("entry", ADAPTER_MATRIX)
def test_execute_rejects_invalid_params(entry: dict[str, Any]) -> None:
    adapter_cls = _load_adapter_class(entry["slug"], entry["class_name"])
    adapter = adapter_cls(mode="airgapped")

    with pytest.raises(ValueError):
        adapter.execute(["invalid"])  # type: ignore[arg-type]
    with pytest.raises(ValueError):
        adapter.execute({"operation": "unsupported"})


def test_hmi_manifests_discoverable_from_registry() -> None:
    manifests = discover_integration_manifests(REPO_ROOT / "packages" / "integrations")
    hmi_slugs = {manifest.slug for manifest in manifests if manifest.domain == "hmi"}
    assert {
        "langfuse",
        "phoenix",
        "explainerdashboard",
        "modelstudio",
        "grafana-with-llm-plugins",
    }.issubset(hmi_slugs)
