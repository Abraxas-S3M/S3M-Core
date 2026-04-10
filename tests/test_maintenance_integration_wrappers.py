"""Unit tests for maintenance integration wrappers.

Military/tactical context:
These tests verify deterministic airgapped behavior for sustainment adapters so
mission readiness decisions remain reliable in disconnected deployments.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path
from typing import Any

import pytest

from packages.integrations.base import IntegrationManifest


ROOT = Path(__file__).resolve().parents[1]
MAINTENANCE_DIR = ROOT / "packages" / "integrations" / "maintenance"

CASES: list[dict[str, str]] = [
    {
        "slug": "militaryassetmanagementsystem",
        "class_name": "MilitaryassetmanagementsystemAdapter",
        "name": "MilitaryAssetManagementSystem",
        "source_url": "https://github.com/chiragSahani/MilitaryAssetManagementSystem",
        "license": "Unknown",
    },
    {
        "slug": "fleetms",
        "class_name": "FleetmsAdapter",
        "name": "fleetms",
        "source_url": "https://github.com/jmnda-dev/fleetms",
        "license": "Unknown",
    },
    {
        "slug": "aws-fleet-predictive-maintenance",
        "class_name": "AwsFleetPredictiveMaintenanceAdapter",
        "name": "aws-fleet-predictive-maintenance",
        "source_url": "https://github.com/awslabs/aws-fleet-predictive-maintenance",
        "license": "Unknown",
    },
    {
        "slug": "ai-powered-predictive-maintenance-system",
        "class_name": "AiPoweredPredictiveMaintenanceAdapter",
        "name": "AI-Powered-Predictive-Maintenance-System-for-Vehicles",
        "source_url": "https://github.com/Siddhartha80/AI-Powered-Predictive-Maintenance-System-for-Vehicles",
        "license": "Unknown",
    },
    {
        "slug": "real-time-predictive-maintenance-system-",
        "class_name": "RealTimePredictiveMaintenanceAdapter",
        "name": "Real-Time-Predictive-Maintenance-System-for-Aircraft",
        "source_url": "https://github.com/EkeminiThompson/Real-Time-Predictive-Maintenance-System-for-Aircraft",
        "license": "Unknown",
    },
]


def _load_adapter_class(slug: str, class_name: str) -> type[Any]:
    adapter_path = MAINTENANCE_DIR / slug / "adapter.py"
    module_name = f"tests.dynamic_maintenance_{slug.replace('-', '_')}_adapter"
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
    assert manifest.domain == "maintenance"
    assert manifest.source_url == case["source_url"]
    assert manifest.license == case["license"]
    assert manifest.integration_type == "adapter"
    assert manifest.airgapped_support is True
    assert adapter.logger.name == f"s3m.integrations.maintenance.{case['slug']}"


@pytest.mark.parametrize("case", CASES, ids=[item["slug"] for item in CASES])
def test_validate_availability_in_airgapped_mode(case: dict[str, str]) -> None:
    adapter_cls = _load_adapter_class(case["slug"], case["class_name"])
    adapter = adapter_cls(mode="airgapped")
    assert adapter.validate_availability() is True


@pytest.mark.parametrize("case", CASES, ids=[item["slug"] for item in CASES])
def test_execute_returns_fixture_in_airgapped_mode(case: dict[str, str]) -> None:
    adapter_cls = _load_adapter_class(case["slug"], case["class_name"])
    adapter = adapter_cls(mode="airgapped")

    response = adapter.execute({"operation": "readiness_check", "priority": "high"})

    assert response["integration_id"] == case["slug"]
    assert response["domain"] == "maintenance"
    assert response["mode"] == "airgapped"
    assert response["source"] == "fixture"
    assert response["status"] == "ok"
    assert response["request"]["operation"] == "readiness_check"
    assert response["request"]["priority"] == "high"
    assert isinstance(response["result"], dict)
    assert response["result"]


@pytest.mark.parametrize("case", CASES, ids=[item["slug"] for item in CASES])
def test_execute_rejects_non_mapping_params(case: dict[str, str]) -> None:
    adapter_cls = _load_adapter_class(case["slug"], case["class_name"])
    adapter = adapter_cls(mode="airgapped")
    with pytest.raises(ValueError, match="dictionary"):
        adapter.execute(params=["invalid"])  # type: ignore[arg-type]
