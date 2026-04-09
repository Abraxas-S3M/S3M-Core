"""Unit tests for military integration wrappers used in tactical rehearsal."""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest
import yaml


PROJECT_ROOT = Path(__file__).resolve().parents[1]
MILITARY_ROOT = PROJECT_ROOT / "packages" / "integrations" / "military"

ADAPTER_SPECS = [
    ("multirobotexploration-robotarmy", "MultirobotexplorationRobotarmyAdapter"),
    ("autonomous-ai-drone-scripts", "AutonomousAiDroneScriptsAdapter"),
    ("aegis", "AegisAdapter"),
    ("autonomous-drone-simulator", "AutonomousDroneSimulatorAdapter"),
    ("autonomous-drone-swarm", "AutonomousDroneSwarmAdapter"),
]


def _load_adapter_class(slug: str, class_name: str):
    module_path = MILITARY_ROOT / slug / "adapter.py"
    module_name = f"test_military_{slug.replace('-', '_')}_adapter"
    spec = importlib.util.spec_from_file_location(module_name, module_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return getattr(module, class_name)


@pytest.mark.parametrize(("slug", "class_name"), ADAPTER_SPECS, ids=[slug for slug, _ in ADAPTER_SPECS])
def test_manifest_is_loaded_from_yaml(slug: str, class_name: str) -> None:
    adapter_cls = _load_adapter_class(slug, class_name)
    adapter = adapter_cls(mode="airgapped")
    manifest = adapter.get_manifest()

    manifest_yaml = MILITARY_ROOT / slug / "manifest.yaml"
    raw = yaml.safe_load(manifest_yaml.read_text(encoding="utf-8"))

    assert manifest.name == raw["name"]
    assert manifest.slug == raw["slug"]
    assert manifest.domain == raw["domain"]
    assert manifest.source_url == raw["source_url"]
    assert manifest.license == raw["license"]


@pytest.mark.parametrize(("slug", "class_name"), ADAPTER_SPECS, ids=[slug for slug, _ in ADAPTER_SPECS])
def test_airgapped_validate_and_execute_use_local_fixture(slug: str, class_name: str) -> None:
    adapter_cls = _load_adapter_class(slug, class_name)
    adapter = adapter_cls(mode="airgapped")

    assert adapter.validate_availability() is True
    result = adapter.execute({"operation": "mission_rehearsal"})
    assert result["integration_id"] == slug
    assert result["mode"] == "airgapped"
    assert result["source"] == "fixture"
    assert result["available"] is True
    assert result["result"]["status"] == "completed"


@pytest.mark.parametrize(("slug", "class_name"), ADAPTER_SPECS, ids=[slug for slug, _ in ADAPTER_SPECS])
def test_logger_name_matches_military_integration_slug(slug: str, class_name: str) -> None:
    adapter_cls = _load_adapter_class(slug, class_name)
    adapter = adapter_cls(mode="airgapped")
    assert adapter.logger.name == f"s3m.integrations.military.{slug}"


@pytest.mark.parametrize(("slug", "class_name"), ADAPTER_SPECS, ids=[slug for slug, _ in ADAPTER_SPECS])
def test_execute_rejects_non_mapping_params(slug: str, class_name: str) -> None:
    adapter_cls = _load_adapter_class(slug, class_name)
    adapter = adapter_cls(mode="airgapped")

    with pytest.raises(ValueError):
        adapter.execute(["unsafe", "params"])
