"""Unit tests for autonomy integration wrappers."""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest


INTEGRATION_CASES = [
    {
        "slug": "intel-xai-tools",
        "class_name": "IntelXaiToolsAdapter",
        "name": "intel-xai-tools",
        "license": "Apache 2.0",
    },
    {
        "slug": "xai-lib",
        "class_name": "XaiLibAdapter",
        "name": "XAI-Lib",
        "license": "MIT",
    },
    {
        "slug": "xai-cybersecurity",
        "class_name": "XaiCybersecurityAdapter",
        "name": "XAI-Cybersecurity",
        "license": "MIT",
    },
    {
        "slug": "groot",
        "class_name": "GrootAdapter",
        "name": "Groot",
        "license": "MIT",
    },
    {
        "slug": "awesome-behavior-trees",
        "class_name": "AwesomeBehaviorTreesAdapter",
        "name": "awesome-behavior-trees",
        "license": "MIT",
    },
]


def _load_adapter_class(slug: str, class_name: str):
    root = Path(__file__).resolve().parents[1]
    adapter_path = root / "packages" / "integrations" / "autonomy" / slug / "adapter.py"
    module_name = f"autonomy_{slug.replace('-', '_')}_adapter"
    spec = importlib.util.spec_from_file_location(module_name, adapter_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return getattr(module, class_name)


@pytest.mark.parametrize("case", INTEGRATION_CASES)
def test_manifest_fields(case: dict[str, str]) -> None:
    adapter_cls = _load_adapter_class(case["slug"], case["class_name"])
    manifest = adapter_cls(mode="airgapped").get_manifest()
    assert manifest.name == case["name"]
    assert manifest.slug == case["slug"]
    assert manifest.domain == "autonomy"
    assert manifest.license == case["license"]


@pytest.mark.parametrize("case", INTEGRATION_CASES)
def test_airgapped_availability_and_execute(case: dict[str, str]) -> None:
    adapter_cls = _load_adapter_class(case["slug"], case["class_name"])
    adapter = adapter_cls(mode="airgapped")

    assert adapter.validate_availability() is True

    out = adapter.execute({"operation": "unit_test_operation"})
    assert out["status"] == "ok"
    assert out["integration_id"] == case["slug"]
    assert out["mode"] == "airgapped"
    assert out["request"]["operation"] == "unit_test_operation"


@pytest.mark.parametrize("case", INTEGRATION_CASES)
def test_logger_name_matches_required_pattern(case: dict[str, str]) -> None:
    adapter_cls = _load_adapter_class(case["slug"], case["class_name"])
    adapter = adapter_cls(mode="airgapped")
    assert adapter.logger.name == f"s3m.integrations.autonomy.{case['slug']}"
