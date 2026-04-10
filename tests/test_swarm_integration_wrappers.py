from __future__ import annotations

import importlib.util
from pathlib import Path
from typing import Any

import pytest


CASES = [
    {
        "slug": "multi-robot-trainer",
        "adapter_path": Path(
            "/workspace/packages/integrations/swarm/multi-robot-trainer/adapter.py"
        ),
        "class_name": "MultiRobotTrainerAdapter",
        "logger_name": "s3m.integrations.swarm.multi-robot-trainer",
        "fixture_probe": ("mission_id", "swarm-train-2026-04-10-01"),
    },
    {
        "slug": "multi-agent-reinforcement-learning-activ",
        "adapter_path": Path(
            "/workspace/packages/integrations/swarm/multi-agent-reinforcement-learning-activ/adapter.py"
        ),
        "class_name": "MultiAgentReinforcementLearningAdapter",
        "logger_name": "s3m.integrations.swarm.multi-agent-reinforcement-learning-activ",
        "fixture_probe": ("team_id", "scout-pack-4"),
    },
    {
        "slug": "open-dis",
        "adapter_path": Path("/workspace/packages/integrations/swarm/open-dis/adapter.py"),
        "class_name": "OpenDisAdapter",
        "logger_name": "s3m.integrations.swarm.open-dis",
        "fixture_probe": ("exercise_id", "joint-federation-west-1"),
    },
    {
        "slug": "odin-c2is",
        "adapter_path": Path("/workspace/packages/integrations/swarm/odin-c2is/adapter.py"),
        "class_name": "Odinc2isAdapter",
        "logger_name": "s3m.integrations.swarm.odin-c2is",
        "fixture_probe": ("headquarters", "joint-task-force-north"),
    },
    {
        "slug": "openc2sim---c2simartifacts",
        "adapter_path": Path(
            "/workspace/packages/integrations/swarm/openc2sim---c2simartifacts/adapter.py"
        ),
        "class_name": "Openc2simC2simartifactsAdapter",
        "logger_name": "s3m.integrations.swarm.openc2sim---c2simartifacts",
        "fixture_probe": ("bundle_id", "brigade-rehearsal-bundle-22"),
    },
]


def _load_adapter_class(adapter_path: Path, class_name: str) -> type[Any]:
    spec = importlib.util.spec_from_file_location(f"s3m_{class_name}_under_test", adapter_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return getattr(module, class_name)


@pytest.mark.parametrize("case", CASES)
def test_manifest_metadata_for_swarm_wrappers(case: dict[str, Any]) -> None:
    adapter_cls = _load_adapter_class(case["adapter_path"], case["class_name"])
    manifest = adapter_cls(mode="airgapped").get_manifest()
    assert manifest.slug == case["slug"]
    assert manifest.domain == "swarm"


@pytest.mark.parametrize("case", CASES)
def test_airgapped_availability_for_swarm_wrappers(case: dict[str, Any]) -> None:
    adapter_cls = _load_adapter_class(case["adapter_path"], case["class_name"])
    assert adapter_cls(mode="airgapped").validate_availability() is True


@pytest.mark.parametrize("case", CASES)
def test_airgapped_execute_returns_fixture_for_swarm_wrappers(case: dict[str, Any]) -> None:
    adapter_cls = _load_adapter_class(case["adapter_path"], case["class_name"])
    adapter = adapter_cls(mode="airgapped")
    response = adapter.execute({"operation": "readiness_check"})
    key, value = case["fixture_probe"]
    assert response["source"] == "fixture"
    assert response["result"][key] == value
    assert adapter.logger.name == case["logger_name"]
