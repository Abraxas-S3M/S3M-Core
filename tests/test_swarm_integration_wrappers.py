"""Unit tests for swarm integration wrappers.

Military/tactical context:
These tests enforce deterministic airgapped behavior for multi-agent mission
control wrappers used in sovereign swarm rehearsal and planning workflows.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path
from typing import Any

import pytest
import yaml

from packages.integrations.base import IntegrationManifest


ROOT = Path(__file__).resolve().parents[1]
SWARM_DIR = ROOT / "packages" / "integrations" / "swarm"

CASES: list[dict[str, str]] = [
    {
        "slug": "amos-autonomous-mission-orchestration-sy",
        "class_name": "AmosAutonomousMissionOrchestrationAdapter",
        "name": "amos-autonomous_mission_orchestration_system",
        "source_url": "https://github.com/merkuriddg/amos-autonomous_mission_orchestration_system",
        "license": "Apache 2.0",
    },
    {
        "slug": "autonomous-uavs-swarm-mission",
        "class_name": "AutonomousUavsSwarmMissionAdapter",
        "name": "Autonomous_UAVs_Swarm_Mission",
        "source_url": "https://github.com/AlexJinlei/Autonomous_UAVs_Swarm_Mission",
        "license": "MIT",
    },
    {
        "slug": "langostino",
        "class_name": "LangostinoAdapter",
        "name": "Langostino",
        "source_url": "https://github.com/swarm-subnet/Langostino",
        "license": "MIT",
    },
    {
        "slug": "droneswarmgpt",
        "class_name": "DroneswarmgptAdapter",
        "name": "DroneSwarmGPT",
        "source_url": "https://github.com/The-Swarm-Corporation/DroneSwarmGPT",
        "license": "Apache 2.0",
    },
    {
        "slug": "ardupilot-multiagent-simulation",
        "class_name": "ArdupilotMultiagentSimulationAdapter",
        "name": "Ardupilot_Multiagent_Simulation",
        "source_url": "https://github.com/aau-cns/Ardupilot_Multiagent_Simulation",
        "license": "GPL-3.0",
    },
]


def _load_adapter_class(slug: str, class_name: str) -> type[Any]:
    adapter_path = SWARM_DIR / slug / "adapter.py"
    module_name = f"tests.dynamic_swarm_{slug.replace('-', '_')}_adapter"
    spec = importlib.util.spec_from_file_location(module_name, adapter_path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return getattr(module, class_name)


@pytest.mark.parametrize("case", CASES, ids=[item["slug"] for item in CASES])
def test_manifest_fields(case: dict[str, str]) -> None:
    adapter_cls = _load_adapter_class(case["slug"], case["class_name"])
    adapter = adapter_cls(mode="airgapped")

    manifest = adapter.get_manifest()
    raw = yaml.safe_load((SWARM_DIR / case["slug"] / "manifest.yaml").read_text(encoding="utf-8"))

    assert isinstance(manifest, IntegrationManifest)
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


@pytest.mark.parametrize("case", CASES, ids=[item["slug"] for item in CASES])
def test_logger_names_follow_swarm_slug(case: dict[str, str]) -> None:
    adapter_cls = _load_adapter_class(case["slug"], case["class_name"])
    adapter = adapter_cls(mode="airgapped")
    assert adapter.logger.name == f"s3m.integrations.swarm.{case['slug']}"


@pytest.mark.parametrize("case", CASES, ids=[item["slug"] for item in CASES])
def test_validate_availability_in_airgapped_mode(case: dict[str, str]) -> None:
    adapter_cls = _load_adapter_class(case["slug"], case["class_name"])
    adapter = adapter_cls(mode="airgapped")
    assert adapter.validate_availability() is True


@pytest.mark.parametrize("case", CASES, ids=[item["slug"] for item in CASES])
def test_execute_returns_fixture_in_airgapped_mode(case: dict[str, str]) -> None:
    adapter_cls = _load_adapter_class(case["slug"], case["class_name"])
    adapter = adapter_cls(mode="airgapped")

    response = adapter.execute({"operation": "swarm_readiness_check", "priority": "high"})

    assert response["integration_id"] == case["slug"]
    assert response["domain"] == "swarm"
    assert response["mode"] == "airgapped"
    assert response["source"] == "fixture"
    assert response["status"] == "ok"
    assert response["operation"] == "swarm_readiness_check"
    assert response["request"]["priority"] == "high"
    assert isinstance(response["result"], dict)
    assert response["result"]


@pytest.mark.parametrize("case", CASES, ids=[item["slug"] for item in CASES])
def test_execute_rejects_non_mapping_params(case: dict[str, str]) -> None:
    adapter_cls = _load_adapter_class(case["slug"], case["class_name"])
    adapter = adapter_cls(mode="airgapped")
    with pytest.raises(ValueError, match="dictionary"):
        adapter.execute(params=["invalid"])  # type: ignore[arg-type]
