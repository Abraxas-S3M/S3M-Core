"""Unit tests for swarm integration adapters.

Military/tactical context:
These tests enforce deterministic, airgapped-safe behavior for swarm wrappers
used in sovereign mission rehearsal and multi-UAV coordination planning.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path
from typing import Any

import pytest
import yaml

from packages.integrations.registry import discover_integration_manifests


REPO_ROOT = Path(__file__).resolve().parents[1]
SWARM_DIR = REPO_ROOT / "packages" / "integrations" / "swarm"

SWARM_CASES: list[dict[str, str]] = [
    {
        "slug": "vswarm",
        "class_name": "VswarmAdapter",
        "name": "vswarm",
        "source_url": "https://github.com/lis-epfl/vswarm",
        "license": "MIT",
    },
    {
        "slug": "coflyers",
        "class_name": "CoflyersAdapter",
        "name": "CoFlyers",
        "source_url": "https://github.com/micros-uav/CoFlyers",
        "license": "MIT",
    },
    {
        "slug": "swarm-formation",
        "class_name": "SwarmFormationAdapter",
        "name": "Swarm-Formation",
        "source_url": "https://github.com/ZJU-FAST-Lab/Swarm-Formation",
        "license": "GPLv3",
    },
    {
        "slug": "multi-robot-ros2",
        "class_name": "MultiRobotRos2Adapter",
        "name": "multi_robot_ros2",
        "source_url": "https://github.com/anhbantre/multi_robot_ros2",
        "license": "MIT",
    },
    {
        "slug": "rai",
        "class_name": "RaiAdapter",
        "name": "rai",
        "source_url": "https://github.com/RobotecAI/rai",
        "license": "MIT",
    },
]


def _load_adapter_class(slug: str, class_name: str) -> type[Any]:
    adapter_path = SWARM_DIR / slug / "adapter.py"
    module_name = f"tests.dynamic_swarm_{slug.replace('-', '_')}_adapter"
    spec = importlib.util.spec_from_file_location(module_name, adapter_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return getattr(module, class_name)


@pytest.mark.parametrize("case", SWARM_CASES, ids=[entry["slug"] for entry in SWARM_CASES])
def test_manifest_fields(case: dict[str, str]) -> None:
    adapter_cls = _load_adapter_class(case["slug"], case["class_name"])
    adapter = adapter_cls(mode="airgapped")
    manifest = adapter.get_manifest()

    raw = yaml.safe_load((SWARM_DIR / case["slug"] / "manifest.yaml").read_text(encoding="utf-8"))

    assert manifest.name == case["name"]
    assert manifest.name == raw["name"]
    assert manifest.slug == case["slug"]
    assert manifest.slug == raw["slug"]
    assert manifest.domain == "swarm"
    assert manifest.domain == raw["domain"]
    assert manifest.source_url == case["source_url"]
    assert manifest.source_url == raw["source_url"]
    assert manifest.license == case["license"]
    assert manifest.license == raw["license"]
    assert manifest.integration_type == "adapter"
    assert manifest.airgapped_support is True


@pytest.mark.parametrize("case", SWARM_CASES, ids=[entry["slug"] for entry in SWARM_CASES])
def test_logger_names_follow_swarm_slug(case: dict[str, str]) -> None:
    adapter_cls = _load_adapter_class(case["slug"], case["class_name"])
    adapter = adapter_cls(mode="airgapped")
    assert adapter.logger.name == f"s3m.integrations.swarm.{case['slug']}"


@pytest.mark.parametrize("case", SWARM_CASES, ids=[entry["slug"] for entry in SWARM_CASES])
def test_airgapped_validate_and_execute(case: dict[str, str]) -> None:
    adapter_cls = _load_adapter_class(case["slug"], case["class_name"])
    adapter = adapter_cls(mode="airgapped")

    assert adapter.validate_availability() is True

    response = adapter.execute({"operation": "unit-test"})
    assert response["status"] == "ok"
    assert response["integration_id"] == case["slug"]
    assert response["domain"] == "swarm"
    assert response["mode"] == "airgapped"
    assert response["source"] == "fixture"
    assert response["operation"] == "unit-test"
    assert response["available"] is True
    assert response["request"] == {"operation": "unit-test"}
    assert isinstance(response["result"], dict)
    assert response["result"]["status"] == "ok"


@pytest.mark.parametrize("case", SWARM_CASES, ids=[entry["slug"] for entry in SWARM_CASES])
def test_execute_rejects_non_mapping_params(case: dict[str, str]) -> None:
    adapter_cls = _load_adapter_class(case["slug"], case["class_name"])
    adapter = adapter_cls(mode="airgapped")

    with pytest.raises(ValueError, match="dictionary"):
        adapter.execute(params=["invalid"])  # type: ignore[arg-type]


def test_swarm_manifests_are_discoverable() -> None:
    manifests = discover_integration_manifests(REPO_ROOT / "packages" / "integrations")
    swarm_slugs = {manifest.slug for manifest in manifests if manifest.domain == "swarm"}
    assert {
        "vswarm",
        "coflyers",
        "swarm-formation",
        "multi-robot-ros2",
        "rai",
    }.issubset(swarm_slugs)
