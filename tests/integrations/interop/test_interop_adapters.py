"""Unit tests for interoperability and simulation-standard adapters.

Military/tactical context:
These tests ensure deterministic adapter behavior for disconnected mission
rehearsal environments where interoperability tooling must remain predictable.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path
from typing import Any

import pytest

from packages.integrations.registry import discover_integration_manifests


REPO_ROOT = Path(__file__).resolve().parents[3]

ADAPTER_CASES: list[dict[str, str]] = [
    {
        "slug_dir": "air-c2-cop-python",
        "class_name": "AirC2CopPythonAdapter",
        "integration_id": "air-c2-cop-python",
        "manifest_name": "air-c2-cop-python",
        "source_url": "https://github.com/Esri/air-c2-cop-python",
        "operation": "cop_snapshot",
    },
    {
        "slug_dir": "ghosts-cyber-range-and-exercise-simulati",
        "class_name": "GhostsCyberRangeAndAdapter",
        "integration_id": "ghosts-cyber-range-and-exercise-simulati",
        "manifest_name": "ghosts-cyber-range-and-exercise-simulation-tools",
        "source_url": "https://github.com/cmu-sei/ghosts-cyber-range-and-exercise-simulation-tools",
        "operation": "range_state_snapshot",
    },
    {
        "slug_dir": "tacticalmesh",
        "class_name": "TacticalmeshAdapter",
        "integration_id": "tacticalmesh",
        "manifest_name": "TacticalMesh",
        "source_url": "https://github.com/TamTunnel/TacticalMesh",
        "operation": "mesh_topology_snapshot",
    },
    {
        "slug_dir": "awesome-command-control",
        "class_name": "AwesomeCommandControlAdapter",
        "integration_id": "awesome-command-control",
        "manifest_name": "awesome-command-control",
        "source_url": "https://github.com/tcostam/awesome-command-control",
        "operation": "catalog_snapshot",
    },
    {
        "slug_dir": "coredsunreal-samples",
        "class_name": "CoredsunrealsamplesAdapter",
        "integration_id": "coredsunreal-samples",
        "manifest_name": "coreDSUnreal (samples)",
        "source_url": "https://github.com/distributedsimulationtools/coreDSUnreal_Sample_AutomaticMode",
        "operation": "entity_state_sync",
    },
]


def _load_adapter_class(slug_dir: str, class_name: str) -> type[Any]:
    adapter_path = REPO_ROOT / "packages" / "integrations" / "interop" / slug_dir / "adapter.py"
    module_name = f"packages.integrations.interop.{slug_dir.replace('-', '_')}.adapter"
    spec = importlib.util.spec_from_file_location(module_name, adapter_path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Unable to load adapter module at {adapter_path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return getattr(module, class_name)


@pytest.mark.parametrize("case", ADAPTER_CASES, ids=[item["integration_id"] for item in ADAPTER_CASES])
def test_manifest_and_logger_fields(case: dict[str, str]) -> None:
    adapter_cls = _load_adapter_class(case["slug_dir"], case["class_name"])
    adapter = adapter_cls(mode="airgapped")

    manifest = adapter.get_manifest()
    assert manifest.name == case["manifest_name"]
    assert manifest.slug == case["integration_id"]
    assert manifest.domain == "interop"
    assert manifest.source_url == case["source_url"]
    assert manifest.license == "Unknown"
    assert manifest.integration_type == "adapter"
    assert manifest.airgapped_support is True
    assert adapter.logger.name == f"s3m.integrations.interop.{case['integration_id']}"


@pytest.mark.parametrize("case", ADAPTER_CASES, ids=[item["integration_id"] for item in ADAPTER_CASES])
def test_validate_availability_true_in_airgapped_mode(case: dict[str, str]) -> None:
    adapter_cls = _load_adapter_class(case["slug_dir"], case["class_name"])
    assert adapter_cls(mode="airgapped").validate_availability() is True


@pytest.mark.parametrize("case", ADAPTER_CASES, ids=[item["integration_id"] for item in ADAPTER_CASES])
def test_execute_returns_fixture_when_airgapped(case: dict[str, str]) -> None:
    adapter_cls = _load_adapter_class(case["slug_dir"], case["class_name"])
    operation = case["operation"]
    response = adapter_cls(mode="airgapped").execute({"operation": operation})

    assert response["integration_id"] == case["integration_id"]
    assert response["domain"] == "interop"
    assert response["mode"] == "airgapped"
    assert response["status"] == "ok"
    assert response["source"] == "fixture"
    assert response["operation"] == operation
    assert response["request"] == {"operation": operation}
    assert isinstance(response["result"], dict)
    assert response["result"]


@pytest.mark.parametrize("case", ADAPTER_CASES, ids=[item["integration_id"] for item in ADAPTER_CASES])
def test_execute_rejects_invalid_params(case: dict[str, str]) -> None:
    adapter_cls = _load_adapter_class(case["slug_dir"], case["class_name"])
    adapter = adapter_cls(mode="airgapped")

    with pytest.raises(ValueError, match="dictionary"):
        adapter.execute(params=["invalid"])  # type: ignore[arg-type]


@pytest.mark.parametrize("case", ADAPTER_CASES, ids=[item["integration_id"] for item in ADAPTER_CASES])
def test_execute_rejects_unsupported_operation(case: dict[str, str]) -> None:
    adapter_cls = _load_adapter_class(case["slug_dir"], case["class_name"])
    adapter = adapter_cls(mode="airgapped")

    with pytest.raises(ValueError, match="Unsupported operation"):
        adapter.execute({"operation": "unsupported"})


def test_interop_manifests_are_discoverable() -> None:
    manifests = discover_integration_manifests(REPO_ROOT / "packages" / "integrations")
    interop_slugs = {manifest.slug for manifest in manifests if manifest.domain == "interop"}
    assert {
        "air-c2-cop-python",
        "ghosts-cyber-range-and-exercise-simulati",
        "tacticalmesh",
        "awesome-command-control",
        "coredsunreal-samples",
    }.issubset(interop_slugs)
