"""Unit tests for maintenance-domain integration wrappers.

Military/tactical context:
These tests verify deterministic adapter behavior for sustainment and
procurement workflows that must remain operational in sovereign, airgapped
deployment conditions.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path
from typing import Any

import pytest
import yaml

from packages.integrations.base import IntegrationManifest


ROOT = Path(__file__).resolve().parents[3]
MAINTENANCE_DIR = ROOT / "packages" / "integrations" / "maintenance"

CASES: list[tuple[str, str, str, str, str]] = [
    (
        "fleetbase",
        "FleetbaseAdapter",
        "fleetbase",
        "https://github.com/fleetbase/fleetbase",
        "maintenance_schedule",
    ),
    (
        "open-msupply",
        "OpenMsupplyAdapter",
        "open-msupply",
        "https://github.com/msupply-foundation/open-msupply",
        "stock_status",
    ),
    (
        "pmx-data",
        "PmxDataAdapter",
        "pmx_data",
        "https://github.com/autonlab/pmx_data",
        "dataset_summary",
    ),
    (
        "predictive-maintenance-with-mlops",
        "PredictiveMaintenanceWithMlopsAdapter",
        "Predictive_Maintenance_With_MLops",
        "https://github.com/Sengarofficial/Predictive_Maintenance_With_MLops",
        "rul_estimation",
    ),
    (
        "ml-based-vehicle-predictive-maintenance-",
        "MlBasedVehiclePredictiveAdapter",
        "ML-Based-Vehicle-Predictive-Maintenance-System-with-Real-Time-Visualization",
        "https://github.com/iDharshan/ML-Based-Vehicle-Predictive-Maintenance-System-with-Real-Time-Visualization",
        "health_prediction",
    ),
]


def _load_adapter_class(slug: str, class_name: str) -> tuple[type[Any], Any]:
    adapter_path = MAINTENANCE_DIR / slug / "adapter.py"
    module_name = f"tests.dynamic_maintenance_{slug.replace('-', '_')}_adapter"
    spec = importlib.util.spec_from_file_location(module_name, adapter_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return getattr(module, class_name), module


@pytest.mark.parametrize(("slug", "class_name", "expected_name", "expected_source_url", "_operation"), CASES)
def test_manifest_fields_and_logger_name(
    slug: str, class_name: str, expected_name: str, expected_source_url: str, _operation: str
) -> None:
    adapter_cls, _module = _load_adapter_class(slug, class_name)
    adapter = adapter_cls(mode="airgapped")
    manifest = adapter.get_manifest()

    manifest_yaml = MAINTENANCE_DIR / slug / "manifest.yaml"
    raw = yaml.safe_load(manifest_yaml.read_text(encoding="utf-8"))

    assert isinstance(manifest, IntegrationManifest)
    assert manifest.name == expected_name
    assert manifest.name == raw["name"]
    assert manifest.slug == slug
    assert manifest.domain == "maintenance"
    assert manifest.source_url == expected_source_url
    assert manifest.license == "Unknown"
    assert manifest.integration_type == "adapter"
    assert adapter.logger.name == f"s3m.integrations.maintenance.{slug}"


@pytest.mark.parametrize(("slug", "class_name", "_expected_name", "_expected_source_url", "_operation"), CASES)
def test_validate_availability_in_airgapped_mode(
    slug: str, class_name: str, _expected_name: str, _expected_source_url: str, _operation: str
) -> None:
    adapter_cls, _module = _load_adapter_class(slug, class_name)
    adapter = adapter_cls(mode="airgapped")
    assert adapter.validate_availability() is True


@pytest.mark.parametrize(("slug", "class_name", "_expected_name", "_expected_source_url", "operation"), CASES)
def test_execute_returns_fixture_payload_in_airgapped_mode(
    slug: str, class_name: str, _expected_name: str, _expected_source_url: str, operation: str
) -> None:
    adapter_cls, _module = _load_adapter_class(slug, class_name)
    adapter = adapter_cls(mode="airgapped")
    output = adapter.execute({"operation": operation})

    assert output["integration_id"] == slug
    assert output["domain"] == "maintenance"
    assert output["mode"] == "airgapped"
    assert output["source"] == "fixture"
    assert output["status"] == "ok"
    assert output["operation"] == operation
    assert isinstance(output["result"], dict)
    assert output["result"].get("status") == "ok"


@pytest.mark.parametrize(("slug", "class_name", "_expected_name", "_expected_source_url", "_operation"), CASES)
def test_validate_availability_online_uses_cli_probe(
    slug: str,
    class_name: str,
    _expected_name: str,
    _expected_source_url: str,
    _operation: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    adapter_cls, module = _load_adapter_class(slug, class_name)
    monkeypatch.setattr(module.shutil, "which", lambda _cmd: "/usr/bin/mock-tool")
    adapter = adapter_cls(mode="online")
    assert adapter.validate_availability() is True


@pytest.mark.parametrize(("slug", "class_name", "_expected_name", "_expected_source_url", "_operation"), CASES)
def test_execute_rejects_invalid_params(
    slug: str, class_name: str, _expected_name: str, _expected_source_url: str, _operation: str
) -> None:
    adapter_cls, _module = _load_adapter_class(slug, class_name)
    adapter = adapter_cls(mode="airgapped")
    with pytest.raises(ValueError, match="dictionary"):
        adapter.execute(["invalid"])  # type: ignore[arg-type]


@pytest.mark.parametrize(("slug", "class_name", "_expected_name", "_expected_source_url", "_operation"), CASES)
def test_execute_rejects_unsupported_operation(
    slug: str, class_name: str, _expected_name: str, _expected_source_url: str, _operation: str
) -> None:
    adapter_cls, _module = _load_adapter_class(slug, class_name)
    adapter = adapter_cls(mode="airgapped")
    with pytest.raises(ValueError, match="Unsupported operation"):
        adapter.execute({"operation": "unsupported"})
