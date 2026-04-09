from __future__ import annotations

import importlib

import pytest


ADAPTER_CASES = [
    {
        "module_path": "packages.integrations.military.drone-swarm.adapter",
        "class_name": "DroneSwarmAdapter",
        "slug": "drone-swarm",
        "name": "drone_swarm",
        "license": "MIT",
    },
    {
        "module_path": "packages.integrations.military.px4-autopilot.adapter",
        "class_name": "Px4AutopilotAdapter",
        "slug": "px4-autopilot",
        "name": "PX4-Autopilot",
        "license": "BSD-3-Clause",
    },
    {
        "module_path": "packages.integrations.military.ardupilot.adapter",
        "class_name": "ArdupilotAdapter",
        "slug": "ardupilot",
        "name": "ardupilot",
        "license": "GPL-3.0",
    },
    {
        "module_path": "packages.integrations.military.orb-slam3.adapter",
        "class_name": "OrbSlam3Adapter",
        "slug": "orb-slam3",
        "name": "ORB_SLAM3",
        "license": "(BSD-style)",
    },
    {
        "module_path": "packages.integrations.military.vins-mono---vins-fusion.adapter",
        "class_name": "VinsMonoVinsAdapter",
        "slug": "vins-mono---vins-fusion",
        "name": "VINS-Mono / VINS-Fusion",
        "license": "(BSD-style)",
    },
]


def _load_adapter(module_path: str, class_name: str):
    module = importlib.import_module(module_path)
    return getattr(module, class_name)


@pytest.mark.parametrize("case", ADAPTER_CASES)
def test_manifest_metadata_is_loaded(case: dict[str, str]):
    adapter_cls = _load_adapter(case["module_path"], case["class_name"])
    manifest = adapter_cls(mode="airgapped").get_manifest()
    assert manifest.slug == case["slug"]
    assert manifest.domain == "military"
    assert manifest.name == case["name"]
    assert manifest.license == case["license"]
    assert manifest.airgapped_support is True


@pytest.mark.parametrize("case", ADAPTER_CASES)
def test_validate_availability_true_in_airgapped_mode(case: dict[str, str]):
    adapter_cls = _load_adapter(case["module_path"], case["class_name"])
    assert adapter_cls(mode="airgapped").validate_availability() is True


@pytest.mark.parametrize("case", ADAPTER_CASES)
def test_execute_returns_fixture_in_airgapped_mode(case: dict[str, str]):
    adapter_cls = _load_adapter(case["module_path"], case["class_name"])
    response = adapter_cls(mode="airgapped").execute({"operation": "status_check"})
    assert response["source"] == "fixture"
    assert response["mode"] == "airgapped"
    assert response["integration_id"] == case["slug"]
    assert isinstance(response["result"], dict)


@pytest.mark.parametrize("case", ADAPTER_CASES)
def test_logger_name_uses_military_slug_namespace(case: dict[str, str]):
    adapter_cls = _load_adapter(case["module_path"], case["class_name"])
    adapter = adapter_cls(mode="airgapped")
    assert adapter.logger.name == f"s3m.integrations.military.{case['slug']}"
