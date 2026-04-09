"""Unit tests for autonomy integration wrappers."""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

from packages.integrations.base import IntegrationAdapter


REPO_ROOT = Path(__file__).resolve().parents[1]
AUTONOMY_ROOT = REPO_ROOT / "packages" / "integrations" / "autonomy"

CASES = [
    (
        "gym-pybullet-drones",
        "GymPybulletDronesAdapter",
        "gym-pybullet-drones",
        "gym-pybullet-drones",
        "MIT",
    ),
    (
        "behaviortree.cpp",
        "BehaviortreecppAdapter",
        "BehaviorTree.CPP",
        "behaviortree.cpp",
        "MIT",
    ),
    (
        "py-trees",
        "PyTreesAdapter",
        "py_trees",
        "py-trees",
        "BSD",
    ),
    (
        "py-trees-ros",
        "PyTreesRosAdapter",
        "py_trees_ros",
        "py-trees-ros",
        "BSD",
    ),
    (
        "behaviortree.ros2",
        "Behaviortreeros2Adapter",
        "BehaviorTree.ROS2",
        "behaviortree.ros2",
        "MIT",
    ),
]


def _load_adapter_class(directory_name: str, class_name: str):
    module_path = AUTONOMY_ROOT / directory_name / "adapter.py"
    module_name = f"autonomy_adapter_{directory_name.replace('-', '_').replace('.', '_')}"
    spec = importlib.util.spec_from_file_location(module_name, module_path)
    if spec is None or spec.loader is None:
        raise AssertionError(f"Unable to build module spec for {module_path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return getattr(module, class_name)


@pytest.mark.parametrize(
    ("directory_name", "class_name", "expected_name", "expected_slug", "expected_license"),
    CASES,
)
def test_manifest_and_airgapped_execution(
    directory_name: str,
    class_name: str,
    expected_name: str,
    expected_slug: str,
    expected_license: str,
) -> None:
    adapter_cls = _load_adapter_class(directory_name, class_name)
    adapter = adapter_cls(mode="airgapped")

    assert isinstance(adapter, IntegrationAdapter)
    assert adapter.integration_id == expected_slug
    assert adapter.domain == "autonomy"
    assert adapter.logger.name == f"s3m.integrations.autonomy.{expected_slug}"

    manifest = adapter.get_manifest()
    assert manifest.name == expected_name
    assert manifest.slug == expected_slug
    assert manifest.domain == "autonomy"
    assert manifest.license == expected_license
    assert manifest.airgapped_support is True

    availability = adapter.validate_availability()
    assert isinstance(availability, bool)

    result = adapter.execute({"mission_id": "test-mission"})
    assert result["mode"] == "airgapped"
    assert result["source"] == "fixture"
    assert result["integration_id"] == expected_slug
    assert isinstance(result["result"], dict)
    assert result["result"]


@pytest.mark.parametrize(("directory_name", "class_name"), [(case[0], case[1]) for case in CASES])
def test_execute_rejects_non_dict_params(directory_name: str, class_name: str) -> None:
    adapter_cls = _load_adapter_class(directory_name, class_name)
    adapter = adapter_cls(mode="airgapped")
    with pytest.raises(ValueError, match="params must be a dictionary"):
        adapter.execute("invalid-input")  # type: ignore[arg-type]
