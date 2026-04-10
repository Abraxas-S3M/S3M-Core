"""Unit tests for sensor-fusion integration wrappers in tactical workflows."""

from __future__ import annotations

import importlib.util
from pathlib import Path
from typing import Any

import pytest
import yaml

from packages.integrations.base import IntegrationManifest


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SENSOR_FUSION_ROOT = PROJECT_ROOT / "packages" / "integrations" / "sensor_fusion"

ADAPTER_CASES: list[dict[str, str]] = [
    {
        "slug": "awesome-threat-detection",
        "class_name": "AwesomeThreatDetectionAdapter",
        "name": "awesome-threat-detection",
        "source_url": "https://github.com/0x4D31/awesome-threat-detection",
        "license": "MIT",
        "operation": "threat_detection_catalog_query",
    },
    {
        "slug": "orion",
        "class_name": "OrionAdapter",
        "name": "orion",
        "source_url": "https://github.com/jonasrenault/orion",
        "license": "MIT",
        "operation": "automated_target_recognition",
    },
    {
        "slug": "smart-track",
        "class_name": "SmartTrackAdapter",
        "name": "smart_track",
        "source_url": "https://github.com/mzahana/smart_track",
        "license": "MIT",
        "operation": "multi_sensor_tracking",
    },
    {
        "slug": "kinematic-arbiter",
        "class_name": "KinematicArbiterAdapter",
        "name": "kinematic_arbiter",
        "source_url": "https://github.com/riscmaster/kinematic_arbiter",
        "license": "MIT",
        "operation": "state_estimation",
    },
    {
        "slug": "fusiontracking",
        "class_name": "FusiontrackingAdapter",
        "name": "FusionTracking",
        "source_url": "https://github.com/TUMFTM/FusionTracking",
        "license": "(Research)",
        "operation": "object_tracking_fusion",
    },
]


def _load_adapter_class(slug: str, class_name: str) -> type[Any]:
    adapter_path = SENSOR_FUSION_ROOT / slug / "adapter.py"
    module_name = f"tests.dynamic_sensor_fusion_{slug.replace('-', '_')}_adapter"
    spec = importlib.util.spec_from_file_location(module_name, adapter_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return getattr(module, class_name)


@pytest.mark.parametrize("case", ADAPTER_CASES, ids=[entry["slug"] for entry in ADAPTER_CASES])
def test_manifest_fields(case: dict[str, str]) -> None:
    adapter_cls = _load_adapter_class(case["slug"], case["class_name"])
    adapter = adapter_cls(mode="airgapped")
    manifest = adapter.get_manifest()

    raw = yaml.safe_load((SENSOR_FUSION_ROOT / case["slug"] / "manifest.yaml").read_text(encoding="utf-8"))

    assert isinstance(manifest, IntegrationManifest)
    assert manifest.name == case["name"]
    assert manifest.name == raw["name"]
    assert manifest.slug == case["slug"]
    assert manifest.slug == raw["slug"]
    assert manifest.domain == "sensor_fusion"
    assert manifest.domain == raw["domain"]
    assert manifest.source_url == case["source_url"]
    assert manifest.source_url == raw["source_url"]
    assert manifest.license == case["license"]
    assert manifest.license == raw["license"]
    assert manifest.integration_type == "adapter"
    assert manifest.airgapped_support is True


@pytest.mark.parametrize("case", ADAPTER_CASES, ids=[entry["slug"] for entry in ADAPTER_CASES])
def test_logger_names_follow_sensor_fusion_slug(case: dict[str, str]) -> None:
    adapter_cls = _load_adapter_class(case["slug"], case["class_name"])
    adapter = adapter_cls(mode="airgapped")
    assert adapter.logger.name == f"s3m.integrations.sensor_fusion.{case['slug']}"


@pytest.mark.parametrize("case", ADAPTER_CASES, ids=[entry["slug"] for entry in ADAPTER_CASES])
def test_airgapped_validate_and_execute(case: dict[str, str]) -> None:
    adapter_cls = _load_adapter_class(case["slug"], case["class_name"])
    adapter = adapter_cls(mode="airgapped")

    assert adapter.validate_availability() is True

    response = adapter.execute({"operation": case["operation"]})
    assert response["status"] == "ok"
    assert response["integration_id"] == case["slug"]
    assert response["domain"] == "sensor_fusion"
    assert response["mode"] == "airgapped"
    assert response["source"] == "fixture"
    assert response["operation"] == case["operation"]
    assert response["available"] is True
    assert isinstance(response["data"], dict)
    assert response["data"]["status"] == "ok"


@pytest.mark.parametrize("case", ADAPTER_CASES, ids=[entry["slug"] for entry in ADAPTER_CASES])
def test_execute_rejects_non_mapping_params(case: dict[str, str]) -> None:
    adapter_cls = _load_adapter_class(case["slug"], case["class_name"])
    adapter = adapter_cls(mode="airgapped")

    with pytest.raises(ValueError, match="dictionary"):
        adapter.execute(params=["unsafe", "params"])  # type: ignore[arg-type]
