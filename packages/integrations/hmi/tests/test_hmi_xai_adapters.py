from __future__ import annotations

import importlib

import pytest


ADAPTER_CASES = [
    {
        "module_path": "packages.integrations.hmi.awesome-explainable-reinforcement-learni.adapter",
        "class_name": "AwesomeExplainableReinforcementLearningAdapter",
        "slug": "awesome-explainable-reinforcement-learni",
        "manifest_name": "awesome-explainable-reinforcement-learning",
        "license": "MIT",
    },
    {
        "module_path": "packages.integrations.hmi.explainable-reinforcement-learning.adapter",
        "class_name": "ExplainableReinforcementLearningAdapter",
        "slug": "explainable-reinforcement-learning",
        "manifest_name": "explainable-reinforcement-learning",
        "license": "MIT",
    },
    {
        "module_path": "packages.integrations.hmi.awesome-xai.adapter",
        "class_name": "AwesomeXaiAdapter",
        "slug": "awesome-xai",
        "manifest_name": "awesome-xai",
        "license": "MIT",
    },
    {
        "module_path": "packages.integrations.hmi.xai-resources.adapter",
        "class_name": "XaiResourcesAdapter",
        "slug": "xai-resources",
        "manifest_name": "xai_resources",
        "license": "MIT",
    },
    {
        "module_path": "packages.integrations.hmi.captum.adapter",
        "class_name": "CaptumAdapter",
        "slug": "captum",
        "manifest_name": "Captum",
        "license": "BSD",
    },
]


def _load_adapter(module_path: str, class_name: str):
    module = importlib.import_module(module_path)
    return getattr(module, class_name)


@pytest.mark.parametrize("case", ADAPTER_CASES)
def test_manifest_metadata_is_loaded(case: dict[str, str]):
    adapter_cls = _load_adapter(case["module_path"], case["class_name"])
    adapter = adapter_cls(mode="airgapped")
    manifest = adapter.get_manifest()
    assert manifest.slug == case["slug"]
    assert manifest.domain == "hmi"
    assert manifest.name == case["manifest_name"]
    assert manifest.license == case["license"]
    assert manifest.airgapped_support is True


@pytest.mark.parametrize("case", ADAPTER_CASES)
def test_validate_availability_true_in_airgapped_mode(case: dict[str, str]):
    adapter_cls = _load_adapter(case["module_path"], case["class_name"])
    adapter = adapter_cls(mode="airgapped")
    assert adapter.validate_availability() is True


@pytest.mark.parametrize("case", ADAPTER_CASES)
def test_execute_returns_fixture_in_airgapped_mode(case: dict[str, str]):
    adapter_cls = _load_adapter(case["module_path"], case["class_name"])
    adapter = adapter_cls(mode="airgapped")
    response = adapter.execute({"operation": "test_operation"})
    assert response["source"] == "fixture"
    assert response["mode"] == "airgapped"
    assert response["integration_id"] == case["slug"]


@pytest.mark.parametrize("case", ADAPTER_CASES)
def test_logger_name_uses_hmi_slug_namespace(case: dict[str, str]):
    adapter_cls = _load_adapter(case["module_path"], case["class_name"])
    adapter = adapter_cls(mode="airgapped")
    assert adapter.logger.name == f"s3m.integrations.hmi.{case['slug']}"
