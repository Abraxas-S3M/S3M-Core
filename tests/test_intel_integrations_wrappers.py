"""Unit tests for intel integration wrappers.

Military/tactical context:
These tests enforce deterministic, airgapped behavior for intelligence
adapters used in sovereign mission-network briefings.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path
from typing import Any

import pytest

from packages.integrations.registry import discover_integration_manifests


REPO_ROOT = Path(__file__).resolve().parents[1]

ADAPTER_CASES: list[dict[str, str]] = [
    {
        "slug_dir": "taiwan-situation",
        "class_name": "TaiwanSituationAdapter",
        "integration_id": "taiwan-situation",
        "manifest_name": "TaiWan-situation",
        "source_url": "https://github.com/Pluto114/TaiWan-situation",
    },
    {
        "slug_dir": "globalpulse",
        "class_name": "GlobalpulseAdapter",
        "integration_id": "globalpulse",
        "manifest_name": "globalpulse",
        "source_url": "https://github.com/ntamero/globalpulse",
    },
    {
        "slug_dir": "crisismap",
        "class_name": "CrisismapAdapter",
        "integration_id": "crisismap",
        "manifest_name": "crisismap",
        "source_url": "https://github.com/realwaynesun/crisismap",
    },
    {
        "slug_dir": "osint-framework",
        "class_name": "OsintFrameworkAdapter",
        "integration_id": "osint-framework",
        "manifest_name": "OSINT-Framework",
        "source_url": "https://github.com/lockfale/OSINT-Framework",
    },
    {
        "slug_dir": "awesome-osint",
        "class_name": "AwesomeOsintAdapter",
        "integration_id": "awesome-osint",
        "manifest_name": "awesome-osint",
        "source_url": "https://github.com/jivoi/awesome-osint",
    },
]


def _load_adapter_class(slug_dir: str, class_name: str) -> type[Any]:
    adapter_path = REPO_ROOT / "packages" / "integrations" / "intel" / slug_dir / "adapter.py"
    module_name = f"packages.integrations.intel.{slug_dir.replace('-', '_')}.adapter"
    spec = importlib.util.spec_from_file_location(module_name, adapter_path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Unable to load adapter module at {adapter_path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return getattr(module, class_name)


@pytest.mark.parametrize("case", ADAPTER_CASES, ids=[item["integration_id"] for item in ADAPTER_CASES])
def test_manifest_and_logger_fields(case: dict[str, str]) -> None:
    adapter_cls = _load_adapter_class(case["slug_dir"], case["class_name"])
    adapter = adapter_cls(mode="airgapped")

    manifest = adapter.get_manifest()
    assert manifest.name == case["manifest_name"]
    assert manifest.slug == case["integration_id"]
    assert manifest.domain == "intel"
    assert manifest.source_url == case["source_url"]
    assert manifest.license == "Unknown"
    assert manifest.integration_type == "adapter"
    assert manifest.airgapped_support is True
    assert adapter.logger.name == f"s3m.integrations.intel.{case['integration_id']}"


@pytest.mark.parametrize("case", ADAPTER_CASES, ids=[item["integration_id"] for item in ADAPTER_CASES])
def test_validate_availability_true_in_airgapped_mode(case: dict[str, str]) -> None:
    adapter_cls = _load_adapter_class(case["slug_dir"], case["class_name"])
    assert adapter_cls(mode="airgapped").validate_availability() is True


@pytest.mark.parametrize("case", ADAPTER_CASES, ids=[item["integration_id"] for item in ADAPTER_CASES])
def test_execute_returns_fixture_when_airgapped(case: dict[str, str]) -> None:
    adapter_cls = _load_adapter_class(case["slug_dir"], case["class_name"])
    response = adapter_cls(mode="airgapped").execute({"operation": "unit-test"})

    assert response["integration_id"] == case["integration_id"]
    assert response["domain"] == "intel"
    assert response["mode"] == "airgapped"
    assert response["source"] == "fixture"
    assert response["operation"] == "unit-test"
    assert response["request"] == {"operation": "unit-test"}
    assert isinstance(response["data"], dict)
    assert response["data"].get("status") == "ok"


@pytest.mark.parametrize("case", ADAPTER_CASES, ids=[item["integration_id"] for item in ADAPTER_CASES])
def test_execute_rejects_invalid_params(case: dict[str, str]) -> None:
    adapter_cls = _load_adapter_class(case["slug_dir"], case["class_name"])
    adapter = adapter_cls(mode="airgapped")

    with pytest.raises(ValueError, match="dictionary"):
        adapter.execute(params=["invalid"])  # type: ignore[arg-type]


def test_intel_manifests_are_discoverable() -> None:
    manifests = discover_integration_manifests(REPO_ROOT / "packages" / "integrations")
    intel_slugs = {manifest.slug for manifest in manifests if manifest.domain == "intel"}
    assert {
        "taiwan-situation",
        "globalpulse",
        "crisismap",
        "osint-framework",
        "awesome-osint",
    }.issubset(intel_slugs)
