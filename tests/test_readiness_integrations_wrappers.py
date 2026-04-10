"""Unit tests for readiness integration wrappers.

Military/tactical context:
These tests enforce deterministic, airgapped behavior for personnel readiness
adapters used by command staff in sovereign mission networks.
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
        "slug_dir": "worldmonitor",
        "class_name": "WorldmonitorAdapter",
        "integration_id": "worldmonitor",
        "manifest_name": "worldmonitor",
        "source_url": "https://github.com/koala73/worldmonitor",
    },
    {
        "slug_dir": "osint-war-room",
        "class_name": "OsintWarRoomAdapter",
        "integration_id": "osint-war-room",
        "manifest_name": "OSINT-War-Room",
        "source_url": "https://github.com/Hue-Jhan/OSINT-War-Room",
    },
    {
        "slug_dir": "orbat-mapper",
        "class_name": "OrbatMapperAdapter",
        "integration_id": "orbat-mapper",
        "manifest_name": "orbat-mapper",
        "source_url": "https://github.com/orbat-mapper/orbat-mapper",
    },
    {
        "slug_dir": "mission-control-dashboard",
        "class_name": "MissionControlDashboardAdapter",
        "integration_id": "mission-control-dashboard",
        "manifest_name": "mission-control-dashboard",
        "source_url": "PatternFly examples on GitHub",
    },
    {
        "slug_dir": "riyaerp-hrms",
        "class_name": "RiyaerpHrmsAdapter",
        "integration_id": "riyaerp-hrms",
        "manifest_name": "RiyaErp-hrms",
        "source_url": "https://github.com/TheLogicIraqCompany/RiyaErp-hrms",
    },
]


def _load_adapter_class(slug_dir: str, class_name: str) -> type[Any]:
    adapter_path = REPO_ROOT / "packages" / "integrations" / "readiness" / slug_dir / "adapter.py"
    module_name = f"packages.integrations.readiness.{slug_dir.replace('-', '_')}.adapter"
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
    assert manifest.domain == "readiness"
    assert manifest.source_url == case["source_url"]
    assert manifest.license == "Unknown"
    assert manifest.integration_type == "adapter"
    assert manifest.airgapped_support is True
    assert adapter.logger.name == f"s3m.integrations.readiness.{case['integration_id']}"


@pytest.mark.parametrize("case", ADAPTER_CASES, ids=[item["integration_id"] for item in ADAPTER_CASES])
def test_validate_availability_true_in_airgapped_mode(case: dict[str, str]) -> None:
    adapter_cls = _load_adapter_class(case["slug_dir"], case["class_name"])
    assert adapter_cls(mode="airgapped").validate_availability() is True


@pytest.mark.parametrize("case", ADAPTER_CASES, ids=[item["integration_id"] for item in ADAPTER_CASES])
def test_execute_returns_fixture_when_airgapped(case: dict[str, str]) -> None:
    adapter_cls = _load_adapter_class(case["slug_dir"], case["class_name"])
    response = adapter_cls(mode="airgapped").execute({"operation": "unit-test"})

    assert response["integration_id"] == case["integration_id"]
    assert response["domain"] == "readiness"
    assert response["mode"] == "airgapped"
    assert response["source"] == "fixture"
    assert response["status"] == "ok"
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


def test_readiness_manifests_are_discoverable() -> None:
    manifests = discover_integration_manifests(REPO_ROOT / "packages" / "integrations")
    readiness_slugs = {manifest.slug for manifest in manifests if manifest.domain == "readiness"}
    assert {
        "worldmonitor",
        "osint-war-room",
        "orbat-mapper",
        "mission-control-dashboard",
        "riyaerp-hrms",
    }.issubset(readiness_slugs)
