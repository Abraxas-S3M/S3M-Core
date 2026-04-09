"""Unit tests for intel integration wrappers in sovereign briefing workflows."""

from __future__ import annotations

import importlib.util
from pathlib import Path
from typing import Any

import pytest
import yaml

from packages.integrations.base import IntegrationManifest


REPO_ROOT = Path(__file__).resolve().parents[1]
INTEL_DIR = REPO_ROOT / "packages" / "integrations" / "intel"

ADAPTER_CASES: list[dict[str, str]] = [
    {
        "slug": "taranis-ai",
        "class_name": "TaranisAiAdapter",
        "logger_name": "s3m.integrations.intel.taranis-ai",
        "operation": "briefing_summary",
    },
    {
        "slug": "meridian",
        "class_name": "MeridianAdapter",
        "logger_name": "s3m.integrations.intel.meridian",
        "operation": "daily_brief",
    },
    {
        "slug": "news-briefing-generator",
        "class_name": "NewsBriefingGeneratorAdapter",
        "logger_name": "s3m.integrations.intel.news-briefing-generator",
        "operation": "generate_brief",
    },
    {
        "slug": "briefing-agent",
        "class_name": "BriefingAgentAdapter",
        "logger_name": "s3m.integrations.intel.briefing-agent",
        "operation": "produce_brief",
    },
    {
        "slug": "awesome-osint-for-everything",
        "class_name": "AwesomeOsintForEverythingAdapter",
        "logger_name": "s3m.integrations.intel.awesome-osint-for-everything",
        "operation": "catalog_lookup",
    },
]


def _load_adapter_class(slug: str, class_name: str) -> type[Any]:
    adapter_path = INTEL_DIR / slug / "adapter.py"
    module_name = f"tests.dynamic_intel_{slug.replace('-', '_')}_adapter"
    spec = importlib.util.spec_from_file_location(module_name, adapter_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return getattr(module, class_name)


@pytest.mark.parametrize("case", ADAPTER_CASES, ids=[item["slug"] for item in ADAPTER_CASES])
def test_manifest_is_loaded_from_yaml(case: dict[str, str]) -> None:
    adapter_cls = _load_adapter_class(case["slug"], case["class_name"])
    adapter = adapter_cls(mode="airgapped")

    manifest = adapter.get_manifest()
    raw = yaml.safe_load((INTEL_DIR / case["slug"] / "manifest.yaml").read_text(encoding="utf-8"))

    assert isinstance(manifest, IntegrationManifest)
    assert manifest.name == raw["name"]
    assert manifest.slug == raw["slug"]
    assert manifest.domain == raw["domain"]
    assert manifest.source_url == raw["source_url"]
    assert manifest.license == raw["license"]
    assert manifest.integration_type == "adapter"
    assert manifest.airgapped_support is True


@pytest.mark.parametrize("case", ADAPTER_CASES, ids=[item["slug"] for item in ADAPTER_CASES])
def test_logger_name_matches_required_pattern(case: dict[str, str]) -> None:
    adapter_cls = _load_adapter_class(case["slug"], case["class_name"])
    adapter = adapter_cls(mode="airgapped")
    assert adapter.logger.name == case["logger_name"]


@pytest.mark.parametrize("case", ADAPTER_CASES, ids=[item["slug"] for item in ADAPTER_CASES])
def test_validate_availability_airgapped_uses_fixture(case: dict[str, str]) -> None:
    adapter_cls = _load_adapter_class(case["slug"], case["class_name"])
    assert adapter_cls(mode="airgapped").validate_availability() is True


@pytest.mark.parametrize("case", ADAPTER_CASES, ids=[item["slug"] for item in ADAPTER_CASES])
def test_execute_airgapped_returns_fixture_payload(case: dict[str, str]) -> None:
    adapter_cls = _load_adapter_class(case["slug"], case["class_name"])
    adapter = adapter_cls(mode="airgapped")

    output = adapter.execute({"operation": case["operation"], "focus": "ops-watch"})

    assert output["integration_id"] == case["slug"]
    assert output["domain"] == "intel"
    assert output["mode"] == "airgapped"
    assert output["source"] == "fixture"
    assert output["available"] is True
    assert output["status"] == "ok"
    assert output["request"]["focus"] == "ops-watch"
    assert isinstance(output["result"], dict)
    assert output["result"]


@pytest.mark.parametrize("case", ADAPTER_CASES, ids=[item["slug"] for item in ADAPTER_CASES])
def test_execute_rejects_invalid_params(case: dict[str, str]) -> None:
    adapter_cls = _load_adapter_class(case["slug"], case["class_name"])
    adapter = adapter_cls(mode="airgapped")
    with pytest.raises(ValueError, match="dictionary"):
        adapter.execute(params="invalid")  # type: ignore[arg-type]
