"""Unit tests for sensor_analytics integration wrappers (Batch 88).

Military/tactical context:
These tests verify deterministic airgapped behavior for remote-sensing adapters
that support maritime and border intelligence workflows in disconnected missions.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path
from typing import Any

import pytest
import yaml

from packages.integrations.base import IntegrationManifest


ROOT = Path(__file__).resolve().parents[3]
SENSOR_ANALYTICS_DIR = ROOT / "packages" / "integrations" / "sensor_analytics"

CASES: list[tuple[str, str, str, str, str]] = [
    (
        "track-my-voyage",
        "TrackMyVoyageAdapter",
        "TRACK-MY-VOYAGE",
        "https://github.com/gopika-10/TRACK-MY-VOYAGE",
        "detect_and_classify_vessels",
    ),
    (
        "sar-shipdet-dataset-processor",
        "SarShipdetDatasetProcessorAdapter",
        "SAR-ShipDet-Dataset-Processor",
        "https://github.com/egshkim/SAR-ShipDet-Dataset-Processor",
        "normalize_sar_ship_datasets",
    ),
    (
        "ship-detection-using-satellite-images",
        "ShipDetectionUsingSatelliteAdapter",
        "Ship-Detection-Using-Satellite-Images",
        "https://github.com/SherinBK/Ship-detection",
        "infer_ships_from_planet_imagery",
    ),
    (
        "border-surveillance-system-variants",
        "BorderSurveillanceSystemvariantsAdapter",
        "Border-Surveillance-System (variants)",
        "Related forks of subhayudas/Border-Surveillance-System",
        "detect_border_anomalies",
    ),
    (
        "awesome-remote-sensing-foundation-models",
        "AwesomeRemoteSensingFoundationAdapter",
        "Awesome-Remote-Sensing-Foundation-Models",
        "https://github.com/Jack-bo1220/Awesome-Remote-Sensing-Foundation-Models",
        "catalog_remote_sensing_foundation_models",
    ),
]


def _load_adapter_class(slug: str, class_name: str) -> tuple[type[Any], Any]:
    adapter_path = SENSOR_ANALYTICS_DIR / slug / "adapter.py"
    module_name = f"tests.dynamic_sensor_analytics_{slug.replace('-', '_')}_adapter"
    spec = importlib.util.spec_from_file_location(module_name, adapter_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return getattr(module, class_name), module


@pytest.mark.parametrize(("slug", "class_name", "expected_name", "expected_source_url", "_operation"), CASES)
def test_manifest_fields_and_logger_name(
    slug: str,
    class_name: str,
    expected_name: str,
    expected_source_url: str,
    _operation: str,
) -> None:
    adapter_cls, _module = _load_adapter_class(slug, class_name)
    adapter = adapter_cls(mode="airgapped")
    manifest = adapter.get_manifest()

    manifest_yaml = SENSOR_ANALYTICS_DIR / slug / "manifest.yaml"
    raw = yaml.safe_load(manifest_yaml.read_text(encoding="utf-8"))

    assert isinstance(manifest, IntegrationManifest)
    assert manifest.name == expected_name
    assert manifest.name == raw["name"]
    assert manifest.slug == slug
    assert manifest.domain == "sensor_analytics"
    assert manifest.source_url == expected_source_url
    assert manifest.license == "Unknown"
    assert manifest.integration_type == "adapter"
    assert manifest.airgapped_support is True
    assert adapter.logger.name == f"s3m.integrations.sensor_analytics.{slug}"


@pytest.mark.parametrize(("slug", "class_name", "_expected_name", "_expected_source_url", "_operation"), CASES)
def test_validate_availability_in_airgapped_mode(
    slug: str,
    class_name: str,
    _expected_name: str,
    _expected_source_url: str,
    _operation: str,
) -> None:
    adapter_cls, _module = _load_adapter_class(slug, class_name)
    adapter = adapter_cls(mode="airgapped")
    assert adapter.validate_availability() is True


@pytest.mark.parametrize(("slug", "class_name", "_expected_name", "_expected_source_url", "operation"), CASES)
def test_execute_returns_fixture_payload_in_airgapped_mode(
    slug: str,
    class_name: str,
    _expected_name: str,
    _expected_source_url: str,
    operation: str,
) -> None:
    adapter_cls, _module = _load_adapter_class(slug, class_name)
    adapter = adapter_cls(mode="airgapped")
    output = adapter.execute({"operation": operation})

    assert output["integration_id"] == slug
    assert output["domain"] == "sensor_analytics"
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
    slug: str,
    class_name: str,
    _expected_name: str,
    _expected_source_url: str,
    _operation: str,
) -> None:
    adapter_cls, _module = _load_adapter_class(slug, class_name)
    adapter = adapter_cls(mode="airgapped")
    with pytest.raises(ValueError, match="dictionary"):
        adapter.execute(["invalid"])  # type: ignore[arg-type]
