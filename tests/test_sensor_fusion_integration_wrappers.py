"""Unit tests for sensor_fusion integration wrappers.

Military/tactical context:
These tests enforce deterministic behavior for sensor-fusion wrappers used in
offline mission rehearsal and threat triage pipelines.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path
from typing import Any

import pytest

from packages.integrations.registry import discover_integration_manifests


REPO_ROOT = Path(__file__).resolve().parents[1]
SENSOR_FUSION_DIR = REPO_ROOT / "packages" / "integrations" / "sensor_fusion"

SENSOR_FUSION_CASES: list[dict[str, str]] = [
    {
        "slug": "military-detect",
        "class_name": "MilitaryDetectAdapter",
        "name": "Military-Detect",
        "source_url": "https://github.com/Erichen911/Military-Detect",
        "license": "MIT",
    },
    {
        "slug": "zeek-anomaly-detector",
        "class_name": "ZeekAnomalyDetectorAdapter",
        "name": "zeek_anomaly_detector",
        "source_url": "https://github.com/stratosphereips/zeek_anomaly_detector",
        "license": "MIT",
    },
    {
        "slug": "machine-learning-based-intrusion-detecti",
        "class_name": "MachineLearningBasedIntrusionAdapter",
        "name": "Machine-Learning-Based-Intrusion-Detection-System",
        "source_url": "https://github.com/uamughal/Machine-Learning-Based-Intrusion-Detection-System",
        "license": "MIT",
    },
    {
        "slug": "uavswarm-dataset",
        "class_name": "UavswarmDatasetAdapter",
        "name": "UAVSwarm-dataset",
        "source_url": "https://github.com/UAVSwarm/UAVSwarm-dataset",
        "license": "MIT",
    },
    {
        "slug": "anomaly-detection-opensearch",
        "class_name": "AnomalyDetectionopensearchAdapter",
        "name": "anomaly-detection (OpenSearch)",
        "source_url": "https://github.com/opensearch-project/anomaly-detection",
        "license": "Apache 2.0",
    },
]


def _load_adapter_class(slug: str, class_name: str) -> type[Any]:
    adapter_path = SENSOR_FUSION_DIR / slug / "adapter.py"
    module_name = f"tests.dynamic_sensor_fusion_{slug.replace('-', '_')}_adapter"
    spec = importlib.util.spec_from_file_location(module_name, adapter_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return getattr(module, class_name)


@pytest.mark.parametrize("case", SENSOR_FUSION_CASES, ids=[entry["slug"] for entry in SENSOR_FUSION_CASES])
def test_manifest_fields(case: dict[str, str]) -> None:
    adapter_cls = _load_adapter_class(case["slug"], case["class_name"])
    adapter = adapter_cls(mode="airgapped")
    manifest = adapter.get_manifest()

    assert manifest.name == case["name"]
    assert manifest.slug == case["slug"]
    assert manifest.domain == "sensor_fusion"
    assert manifest.source_url == case["source_url"]
    assert manifest.license == case["license"]
    assert manifest.airgapped_support is True


@pytest.mark.parametrize("case", SENSOR_FUSION_CASES, ids=[entry["slug"] for entry in SENSOR_FUSION_CASES])
def test_logger_names_follow_sensor_fusion_slug(case: dict[str, str]) -> None:
    adapter_cls = _load_adapter_class(case["slug"], case["class_name"])
    adapter = adapter_cls(mode="airgapped")
    assert adapter.logger.name == f"s3m.integrations.sensor_fusion.{case['slug']}"


@pytest.mark.parametrize("case", SENSOR_FUSION_CASES, ids=[entry["slug"] for entry in SENSOR_FUSION_CASES])
def test_airgapped_validate_and_execute(case: dict[str, str]) -> None:
    adapter_cls = _load_adapter_class(case["slug"], case["class_name"])
    adapter = adapter_cls(mode="airgapped")

    assert adapter.validate_availability() is True

    response = adapter.execute({"operation": "unit-test"})
    assert response["status"] == "ok"
    assert response["integration_id"] == case["slug"]
    assert response["domain"] == "sensor_fusion"
    assert response["mode"] == "airgapped"
    assert response["source"] == "fixture"
    assert response["operation"] == "unit-test"
    assert response["request"] == {"operation": "unit-test"}
    assert isinstance(response["result"], dict)
    assert response["result"]


@pytest.mark.parametrize("case", SENSOR_FUSION_CASES, ids=[entry["slug"] for entry in SENSOR_FUSION_CASES])
def test_execute_rejects_non_mapping_params(case: dict[str, str]) -> None:
    adapter_cls = _load_adapter_class(case["slug"], case["class_name"])
    adapter = adapter_cls(mode="airgapped")

    with pytest.raises(ValueError, match="dictionary"):
        adapter.execute(params=["invalid"])  # type: ignore[arg-type]


def test_sensor_fusion_manifests_are_discoverable() -> None:
    manifests = discover_integration_manifests(REPO_ROOT / "packages" / "integrations")
    sensor_fusion_slugs = {manifest.slug for manifest in manifests if manifest.domain == "sensor_fusion"}
    assert {
        "military-detect",
        "zeek-anomaly-detector",
        "machine-learning-based-intrusion-detecti",
        "uavswarm-dataset",
        "anomaly-detection-opensearch",
    }.issubset(sensor_fusion_slugs)
