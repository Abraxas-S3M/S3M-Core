"""Unit tests for navigation integration wrappers used in tactical mission rehearsal."""

from __future__ import annotations

import importlib.util
from pathlib import Path
from typing import Any

import pytest
import yaml


PROJECT_ROOT = Path(__file__).resolve().parents[1]
NAVIGATION_ROOT = PROJECT_ROOT / "packages" / "integrations" / "navigation"

NAVIGATION_CASES: list[dict[str, str]] = [
    {
        "slug": "sc-lio-sam",
        "class_name": "ScLioSamAdapter",
        "name": "SC-LIO-SAM",
        "source_url": "https://github.com/gisbi-kim/SC-LIO-SAM",
        "license": "(BSD-style)",
    },
    {
        "slug": "li-slam-ros2",
        "class_name": "LiSlamRos2Adapter",
        "name": "li_slam_ros2",
        "source_url": "https://github.com/rsasaki0109/li_slam_ros2",
        "license": "(ROS2-style)",
    },
    {
        "slug": "autonomous-drone-navigation",
        "class_name": "AutonomousDroneNavigationAdapter",
        "name": "Autonomous-drone-navigation",
        "source_url": "https://github.com/ahmedeltaher/Autonomous-drone-navigation",
        "license": "MIT",
    },
    {
        "slug": "visual-slam-ros2",
        "class_name": "VisualSlamRos2Adapter",
        "name": "visual-slam-ros2",
        "source_url": "https://github.com/imnuman/visual-slam-ros2",
        "license": "MIT",
    },
    {
        "slug": "vslam-uav",
        "class_name": "VslamUavAdapter",
        "name": "VSLAM-UAV",
        "source_url": "https://github.com/bandofpv/VSLAM-UAV",
        "license": "MIT",
    },
]


def _load_adapter_class(slug: str, class_name: str) -> type[Any]:
    adapter_path = NAVIGATION_ROOT / slug / "adapter.py"
    module_name = f"tests.dynamic_navigation_{slug.replace('-', '_')}_adapter"
    spec = importlib.util.spec_from_file_location(module_name, adapter_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return getattr(module, class_name)


@pytest.mark.parametrize("case", NAVIGATION_CASES, ids=[entry["slug"] for entry in NAVIGATION_CASES])
def test_manifest_fields(case: dict[str, str]) -> None:
    adapter_cls = _load_adapter_class(case["slug"], case["class_name"])
    adapter = adapter_cls(mode="airgapped")
    manifest = adapter.get_manifest()

    raw = yaml.safe_load((NAVIGATION_ROOT / case["slug"] / "manifest.yaml").read_text(encoding="utf-8"))

    assert manifest.name == case["name"]
    assert manifest.name == raw["name"]
    assert manifest.slug == case["slug"]
    assert manifest.slug == raw["slug"]
    assert manifest.domain == "navigation"
    assert manifest.domain == raw["domain"]
    assert manifest.source_url == case["source_url"]
    assert manifest.source_url == raw["source_url"]
    assert manifest.license == case["license"]
    assert manifest.license == raw["license"]
    assert manifest.integration_type == "adapter"
    assert manifest.airgapped_support is True


@pytest.mark.parametrize("case", NAVIGATION_CASES, ids=[entry["slug"] for entry in NAVIGATION_CASES])
def test_logger_names_follow_navigation_slug(case: dict[str, str]) -> None:
    adapter_cls = _load_adapter_class(case["slug"], case["class_name"])
    adapter = adapter_cls(mode="airgapped")
    assert adapter.logger.name == f"s3m.integrations.navigation.{case['slug']}"


@pytest.mark.parametrize("case", NAVIGATION_CASES, ids=[entry["slug"] for entry in NAVIGATION_CASES])
def test_airgapped_validate_and_execute(case: dict[str, str]) -> None:
    adapter_cls = _load_adapter_class(case["slug"], case["class_name"])
    adapter = adapter_cls(mode="airgapped")

    assert adapter.validate_availability() is True

    response = adapter.execute({"operation": "unit_test_navigation_check"})
    assert response["status"] == "ok"
    assert response["integration_id"] == case["slug"]
    assert response["domain"] == "navigation"
    assert response["mode"] == "airgapped"
    assert response["source"] == "fixture"
    assert response["operation"] == "unit_test_navigation_check"
    assert response["available"] is True
    assert isinstance(response["data"], dict)
    assert response["data"]["status"] == "ok"


@pytest.mark.parametrize("case", NAVIGATION_CASES, ids=[entry["slug"] for entry in NAVIGATION_CASES])
def test_execute_rejects_non_mapping_params(case: dict[str, str]) -> None:
    adapter_cls = _load_adapter_class(case["slug"], case["class_name"])
    adapter = adapter_cls(mode="airgapped")

    with pytest.raises(ValueError, match="dictionary"):
        adapter.execute(params=["unsafe", "params"])  # type: ignore[arg-type]
