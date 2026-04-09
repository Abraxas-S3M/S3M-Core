"""Unit tests for autonomy integration wrappers."""

from __future__ import annotations

import importlib

import pytest


INTEGRATIONS = [
    {
        "module": "packages.integrations.autonomy.nav2-behavior-tree.adapter",
        "class_name": "Nav2BehaviorTreeAdapter",
        "name": "nav2_behavior_tree",
        "slug": "nav2-behavior-tree",
        "source_url": "https://github.com/ros-planning/navigation2(nav2_behavior_tree",
        "license": "BSD",
    },
    {
        "module": "packages.integrations.autonomy.spot-bt-ros.adapter",
        "class_name": "SpotBtRosAdapter",
        "name": "spot_bt_ros",
        "slug": "spot-bt-ros",
        "source_url": "https://github.com/sandialabs/spot_bt_ros",
        "license": "Apache 2.0",
    },
    {
        "module": "packages.integrations.autonomy.pr-behavior-tree.adapter",
        "class_name": "PrBehaviorTreeAdapter",
        "name": "pr_behavior_tree",
        "slug": "pr-behavior-tree",
        "source_url": "https://github.com/personalrobotics/pr_behavior_tree",
        "license": "MIT",
    },
    {
        "module": "packages.integrations.autonomy.xai-ethicalml.adapter",
        "class_name": "XaiethicalmlAdapter",
        "name": "xai (EthicalML)",
        "slug": "xai-ethicalml",
        "source_url": "https://github.com/EthicalML/xai",
        "license": "MIT",
    },
    {
        "module": "packages.integrations.autonomy.trustyai-explainability.adapter",
        "class_name": "TrustyaiExplainabilityAdapter",
        "name": "trustyai-explainability",
        "slug": "trustyai-explainability",
        "source_url": "https://github.com/trustyai-explainability/trustyai-explainability",
        "license": "Apache 2.0",
    },
]


def _load_adapter_class(module_path: str, class_name: str):
    module = importlib.import_module(module_path)
    return getattr(module, class_name)


@pytest.mark.parametrize("entry", INTEGRATIONS)
def test_manifest_fields(entry: dict[str, str]) -> None:
    adapter_cls = _load_adapter_class(entry["module"], entry["class_name"])
    adapter = adapter_cls(mode="airgapped")
    manifest = adapter.get_manifest()

    assert manifest.name == entry["name"]
    assert manifest.slug == entry["slug"]
    assert manifest.domain == "autonomy"
    assert manifest.source_url == entry["source_url"]
    assert manifest.license == entry["license"]
    assert manifest.integration_type == "adapter"
    assert manifest.airgapped_support is True


@pytest.mark.parametrize("entry", INTEGRATIONS)
def test_logger_name_uses_autonomy_slug(entry: dict[str, str]) -> None:
    adapter_cls = _load_adapter_class(entry["module"], entry["class_name"])
    adapter = adapter_cls(mode="airgapped")
    assert adapter.logger.name == f"s3m.integrations.autonomy.{entry['slug']}"


@pytest.mark.parametrize("entry", INTEGRATIONS)
def test_airgapped_mode_uses_fixtures(entry: dict[str, str]) -> None:
    adapter_cls = _load_adapter_class(entry["module"], entry["class_name"])
    adapter = adapter_cls(mode="airgapped")

    assert adapter.validate_availability() is True

    payload = adapter.execute({"action": "unit-test-action"})
    assert payload["integration_id"] == entry["slug"]
    assert payload["execution_mode"] == "airgapped"
    assert payload["requested_action"] == "unit-test-action"
