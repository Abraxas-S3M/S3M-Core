"""Unit tests for sensor_fusion-domain integration wrappers (batch 82).

Military/tactical context:
These tests verify deterministic, offline-safe adapter behavior so sensor
fusion workflows remain reliable in sovereign and contested environments.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path
from typing import Any

import pytest
import yaml

from packages.integrations.base import IntegrationManifest


ROOT = Path(__file__).resolve().parents[3]
SENSOR_FUSION_DIR = ROOT / "packages" / "integrations" / "sensor_fusion"

CASES: list[tuple[str, str, str, str, str, str]] = [
    (
        "drone-anomaly-detection-dataset-and-unsu",
        "DroneAnomalyDetectionDatasetAdapter",
        "Drone-Anomaly-Detection-Dataset-and-Unsupervised-Machine-Learning",
        "https://github.com/isot-lab/Drone-Anomaly-Detection-Dataset-and-Unsupervised-Machine-Learning",
        "MIT",
        "anomaly_score",
    ),
    (
        "ai-driven-threat-detection-system",
        "AiDrivenThreatDetectionAdapter",
        "AI-Driven-Threat-Detection-System",
        "https://github.com/melisa48/AI-Driven-Threat-Detection-System",
        "MIT",
        "anomaly_score",
    ),
    (
        "truth-zeeker-ai-public",
        "TruthZeekerAiPublicAdapter",
        "Truth-Zeeker-AI-Public",
        "https://github.com/dr-rakshith-truth-zeeker/Truth-Zeeker-AI-Public",
        "MIT",
        "anomaly_score",
    ),
    (
        "ros-perception",
        "RosPerceptionAdapter",
        "ros-perception",
        "https://github.com/ros-perception",
        "BSD",
        "pipeline_status",
    ),
    (
        "perception-interfaces",
        "PerceptionInterfacesAdapter",
        "perception_interfaces",
        "https://github.com/ika-rwth-aachen/perception_interfaces",
        "MIT",
        "interface_status",
    ),
]


def _load_adapter_class(slug: str, class_name: str) -> tuple[type[Any], Any]:
    adapter_path = SENSOR_FUSION_DIR / slug / "adapter.py"
    module_name = f"tests.dynamic_sensor_fusion_{slug.replace('-', '_')}_adapter"
    spec = importlib.util.spec_from_file_location(module_name, adapter_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return getattr(module, class_name), module


@pytest.mark.parametrize(("slug", "class_name", "expected_name", "expected_source_url", "license_name", "_operation"), CASES)
def test_manifest_fields_and_logger_name(
    slug: str,
    class_name: str,
    expected_name: str,
    expected_source_url: str,
    license_name: str,
    _operation: str,
) -> None:
    adapter_cls, _module = _load_adapter_class(slug, class_name)
    adapter = adapter_cls(mode="airgapped")
    manifest = adapter.get_manifest()

    manifest_yaml = SENSOR_FUSION_DIR / slug / "manifest.yaml"
    raw = yaml.safe_load(manifest_yaml.read_text(encoding="utf-8"))

    assert isinstance(manifest, IntegrationManifest)
    assert manifest.name == expected_name
    assert manifest.name == raw["name"]
    assert manifest.slug == slug
    assert manifest.domain == "sensor_fusion"
    assert manifest.source_url == expected_source_url
    assert manifest.license == license_name
    assert manifest.integration_type == "adapter"
    assert manifest.airgapped_support is True
    assert adapter.logger.name == f"s3m.integrations.sensor_fusion.{slug}"


@pytest.mark.parametrize(("slug", "class_name", "_expected_name", "_expected_source_url", "_license_name", "_operation"), CASES)
def test_validate_availability_in_airgapped_mode(
    slug: str,
    class_name: str,
    _expected_name: str,
    _expected_source_url: str,
    _license_name: str,
    _operation: str,
) -> None:
    adapter_cls, _module = _load_adapter_class(slug, class_name)
    adapter = adapter_cls(mode="airgapped")
    assert adapter.validate_availability() is True


@pytest.mark.parametrize(("slug", "class_name", "_expected_name", "_expected_source_url", "_license_name", "operation"), CASES)
def test_execute_returns_fixture_payload_in_airgapped_mode(
    slug: str,
    class_name: str,
    _expected_name: str,
    _expected_source_url: str,
    _license_name: str,
    operation: str,
) -> None:
    adapter_cls, _module = _load_adapter_class(slug, class_name)
    adapter = adapter_cls(mode="airgapped")
    output = adapter.execute({"operation": operation})

    assert output["integration_id"] == slug
    assert output["domain"] == "sensor_fusion"
    assert output["mode"] == "airgapped"
    assert output["source"] == "fixture"
    assert output["status"] == "ok"
    assert output["operation"] == operation
    assert isinstance(output["result"], dict)
    assert output["result"].get("status") == "ok"


@pytest.mark.parametrize(("slug", "class_name", "_expected_name", "_expected_source_url", "_license_name", "_operation"), CASES)
def test_validate_availability_online_uses_cli_probe(
    slug: str,
    class_name: str,
    _expected_name: str,
    _expected_source_url: str,
    _license_name: str,
    _operation: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    adapter_cls, module = _load_adapter_class(slug, class_name)
    monkeypatch.setattr(module.shutil, "which", lambda _cmd: "/usr/bin/mock-tool")
    adapter = adapter_cls(mode="online")
    assert adapter.validate_availability() is True


@pytest.mark.parametrize(("slug", "class_name", "_expected_name", "_expected_source_url", "_license_name", "_operation"), CASES)
def test_execute_rejects_invalid_params(
    slug: str,
    class_name: str,
    _expected_name: str,
    _expected_source_url: str,
    _license_name: str,
    _operation: str,
) -> None:
    adapter_cls, _module = _load_adapter_class(slug, class_name)
    adapter = adapter_cls(mode="airgapped")
    with pytest.raises(ValueError, match="dictionary"):
        adapter.execute(["invalid"])  # type: ignore[arg-type]


@pytest.mark.parametrize(("slug", "class_name", "_expected_name", "_expected_source_url", "_license_name", "_operation"), CASES)
def test_execute_rejects_unsupported_operation(
    slug: str,
    class_name: str,
    _expected_name: str,
    _expected_source_url: str,
    _license_name: str,
    _operation: str,
) -> None:
    adapter_cls, _module = _load_adapter_class(slug, class_name)
    adapter = adapter_cls(mode="airgapped")
    with pytest.raises(ValueError, match="Unsupported operation"):
        adapter.execute({"operation": "unsupported"})
