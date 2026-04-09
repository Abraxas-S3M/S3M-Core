"""Tests for intel integration wrappers used in mission OSINT briefings."""

from __future__ import annotations

import importlib.util
from pathlib import Path
from typing import Any

import pytest

from packages.integrations.base import IntegrationManifest


ROOT = Path(__file__).resolve().parents[1]
INTEL_DIR = ROOT / "packages" / "integrations" / "intel"

CASES: list[dict[str, str]] = [
    {
        "slug": "osint-stuff-tool-collection",
        "class_name": "OsintStuffToolCollectionAdapter",
        "name": "osint_stuff_tool_collection",
        "source_url": "https://github.com/cipher387/osint_stuff_tool_collection",
    },
    {
        "slug": "legendary-osint",
        "class_name": "LegendaryOsintAdapter",
        "name": "Legendary_OSINT",
        "source_url": "https://github.com/K2SOsint/Legendary_OSINT",
    },
    {
        "slug": "osint-bible",
        "class_name": "OsintBibleAdapter",
        "name": "OSINT-BIBLE",
        "source_url": "https://github.com/frangelbarrera/OSINT-BIBLE",
    },
    {
        "slug": "arabic-abstractive-summarization",
        "class_name": "ArabicAbstractiveSummarizationAdapter",
        "name": "Arabic-Abstractive-Summarization",
        "source_url": "https://github.com/JoeFarag-00/Arabic-Abstractive-Summarization",
    },
    {
        "slug": "a-hybrid-arabic-text-summarization-appro",
        "class_name": "AHybridArabicTextAdapter",
        "name": "A-Hybrid-Arabic-Text-Summarization-Approach-based-on-Transformers",
        "source_url": "https://github.com/mohamedehab00/A-Hybrid-Arabic-Text-Summarization-Approach-based-on-Transformers",
    },
]


def _load_adapter_class(slug: str, class_name: str) -> type[Any]:
    adapter_path = INTEL_DIR / slug / "adapter.py"
    module_name = f"tests.dynamic_intel_{slug.replace('-', '_')}_adapter"
    spec = importlib.util.spec_from_file_location(module_name, adapter_path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return getattr(module, class_name)


@pytest.mark.parametrize("case", CASES, ids=[item["slug"] for item in CASES])
def test_manifest_fields(case: dict[str, str]) -> None:
    adapter_cls = _load_adapter_class(case["slug"], case["class_name"])
    adapter = adapter_cls(mode="airgapped")

    manifest = adapter.get_manifest()

    assert isinstance(manifest, IntegrationManifest)
    assert manifest.name == case["name"]
    assert manifest.slug == case["slug"]
    assert manifest.domain == "intel"
    assert manifest.source_url == case["source_url"]
    assert manifest.license == "Unknown"
    assert manifest.airgapped_support is True
    assert adapter.logger.name == f"s3m.integrations.intel.{case['slug']}"


@pytest.mark.parametrize("case", CASES, ids=[item["slug"] for item in CASES])
def test_validate_availability_in_airgapped_mode(case: dict[str, str]) -> None:
    adapter_cls = _load_adapter_class(case["slug"], case["class_name"])
    adapter = adapter_cls(mode="airgapped")
    assert adapter.validate_availability() is True


@pytest.mark.parametrize("case", CASES, ids=[item["slug"] for item in CASES])
def test_execute_returns_fixture_in_airgapped_mode(case: dict[str, str]) -> None:
    adapter_cls = _load_adapter_class(case["slug"], case["class_name"])
    adapter = adapter_cls(mode="airgapped")

    response = adapter.execute({"operation": "intel_brief", "priority": "high"})

    assert response["integration_id"] == case["slug"]
    assert response["domain"] == "intel"
    assert response["mode"] == "airgapped"
    assert response["source"] == "fixture"
    assert response["request"]["operation"] == "intel_brief"
    assert response["request"]["priority"] == "high"
    assert isinstance(response["result"], dict)
    assert response["result"]


@pytest.mark.parametrize("case", CASES, ids=[item["slug"] for item in CASES])
def test_execute_rejects_non_mapping_params(case: dict[str, str]) -> None:
    adapter_cls = _load_adapter_class(case["slug"], case["class_name"])
    adapter = adapter_cls(mode="airgapped")
    with pytest.raises(ValueError, match="dictionary"):
        adapter.execute(params=["invalid"])  # type: ignore[arg-type]
