"""Unit tests for HMI integration wrappers in tactical AI assurance workflows."""

from __future__ import annotations

import importlib.util
from pathlib import Path
from typing import Any

import pytest
import yaml

from packages.integrations.base import IntegrationManifest


PROJECT_ROOT = Path(__file__).resolve().parents[1]
HMI_ROOT = PROJECT_ROOT / "packages" / "integrations" / "hmi"

ADAPTER_CASES: list[dict[str, str]] = [
    {
        "slug": "awesome-explainable-ai",
        "class_name": "AwesomeExplainableAiAdapter",
        "logger_name": "s3m.integrations.hmi.awesome-explainable-ai",
    }
]


def _load_adapter_class(slug: str, class_name: str) -> type[Any]:
    adapter_path = HMI_ROOT / slug / "adapter.py"
    module_name = f"tests.dynamic_{slug.replace('-', '_')}_adapter"
    spec = importlib.util.spec_from_file_location(module_name, adapter_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return getattr(module, class_name)


@pytest.mark.parametrize("case", ADAPTER_CASES, ids=[case["slug"] for case in ADAPTER_CASES])
def test_manifest_loaded_from_yaml(case: dict[str, str]) -> None:
    adapter_cls = _load_adapter_class(case["slug"], case["class_name"])
    adapter = adapter_cls(mode="airgapped")
    manifest = adapter.get_manifest()

    raw = yaml.safe_load((HMI_ROOT / case["slug"] / "manifest.yaml").read_text(encoding="utf-8"))

    assert isinstance(manifest, IntegrationManifest)
    assert manifest.name == raw["name"]
    assert manifest.slug == raw["slug"]
    assert manifest.domain == raw["domain"]
    assert manifest.source_url == raw["source_url"]
    assert manifest.license == raw["license"]
    assert manifest.description == raw["description"]
    assert manifest.integration_type == "adapter"
    assert manifest.airgapped_support is True
    assert adapter.logger.name == case["logger_name"]


@pytest.mark.parametrize("case", ADAPTER_CASES, ids=[case["slug"] for case in ADAPTER_CASES])
def test_validate_availability_returns_true_in_airgapped_mode(case: dict[str, str]) -> None:
    adapter_cls = _load_adapter_class(case["slug"], case["class_name"])
    adapter = adapter_cls(mode="airgapped")
    assert adapter.validate_availability() is True


@pytest.mark.parametrize("case", ADAPTER_CASES, ids=[case["slug"] for case in ADAPTER_CASES])
def test_execute_returns_fixture_response_in_airgapped_mode(case: dict[str, str]) -> None:
    adapter_cls = _load_adapter_class(case["slug"], case["class_name"])
    adapter = adapter_cls(mode="airgapped")

    response = adapter.execute({"operation": "xai_frontier_brief"})

    assert response["integration_id"] == case["slug"]
    assert response["domain"] == "hmi"
    assert response["mode"] == "airgapped"
    assert response["source"] == "fixture"
    assert response["operation"] == "xai_frontier_brief"
    assert response["available"] is True
    assert isinstance(response["data"], dict)
    assert response["data"]["status"] == "ok"
    assert isinstance(response["data"]["frontier_methods"], list)
    assert response["data"]["frontier_methods"]


@pytest.mark.parametrize("case", ADAPTER_CASES, ids=[case["slug"] for case in ADAPTER_CASES])
def test_execute_rejects_non_mapping_params(case: dict[str, str]) -> None:
    adapter_cls = _load_adapter_class(case["slug"], case["class_name"])
    adapter = adapter_cls(mode="airgapped")

    with pytest.raises(ValueError, match="mapping|dictionary"):
        adapter.execute(params="unsafe-input")  # type: ignore[arg-type]
