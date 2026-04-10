"""Unit tests for simulation integration wrappers.

Military/tactical context:
These tests ensure simulation adapters provide deterministic airgapped outputs
so mission rehearsal cells can run sovereign training loops without external
service dependencies.
"""

from __future__ import annotations

import importlib
from pathlib import Path
from typing import Any

import pytest
import yaml

from packages.integrations.base import IntegrationManifest


CASES: list[dict[str, str]] = [
    {
        "slug": "pycmo",
        "class_name": "PycmoAdapter",
        "module_name": "packages.integrations.simulation.pycmo.adapter",
        "source_url": "https://github.com/duyminh1998/pycmo",
        "license": "MIT",
    },
    {
        "slug": "panopticon",
        "class_name": "PanopticonAdapter",
        "module_name": "packages.integrations.simulation.panopticon.adapter",
        "source_url": "https://github.com/Panopticon-AI-team/panopticon",
        "license": "MIT",
    },
    {
        "slug": "airsim",
        "class_name": "AirsimAdapter",
        "module_name": "packages.integrations.simulation.airsim.adapter",
        "source_url": "https://github.com/microsoft/AirSim",
        "license": "MIT",
    },
    {
        "slug": "rotors-simulator",
        "class_name": "RotorsSimulatorAdapter",
        "module_name": "packages.integrations.simulation.rotors-simulator.adapter",
        "source_url": "https://github.com/ethz-asl/rotors_simulator",
        "license": "(BSD-style)",
    },
    {
        "slug": "flightmare",
        "class_name": "FlightmareAdapter",
        "module_name": "packages.integrations.simulation.flightmare.adapter",
        "source_url": "https://github.com/uzh-rpg/flightmare",
        "license": "(BSD-style)",
    },
]


def _load_adapter_class(module_name: str, class_name: str) -> type[Any]:
    module = importlib.import_module(module_name)
    return getattr(module, class_name)


@pytest.mark.parametrize("case", CASES, ids=[item["slug"] for item in CASES])
def test_manifest_fields_and_logger(case: dict[str, str]) -> None:
    adapter_cls = _load_adapter_class(case["module_name"], case["class_name"])
    adapter = adapter_cls(mode="airgapped")
    manifest = adapter.get_manifest()

    module_path = Path(importlib.import_module(case["module_name"]).__file__).resolve()
    manifest_yaml = yaml.safe_load((module_path.parent / "manifest.yaml").read_text(encoding="utf-8"))
    assert isinstance(manifest_yaml, dict)

    assert isinstance(manifest, IntegrationManifest)
    assert manifest.name == manifest_yaml["name"]
    assert manifest.slug == case["slug"]
    assert manifest.domain == "simulation"
    assert manifest.source_url == case["source_url"]
    assert manifest.license == case["license"]
    assert manifest.airgapped_support is True
    assert adapter.logger.name == f"s3m.integrations.simulation.{case['slug']}"


@pytest.mark.parametrize("case", CASES, ids=[item["slug"] for item in CASES])
def test_validate_availability_true_in_airgapped_mode(case: dict[str, str]) -> None:
    adapter_cls = _load_adapter_class(case["module_name"], case["class_name"])
    assert adapter_cls(mode="airgapped").validate_availability() is True


@pytest.mark.parametrize("case", CASES, ids=[item["slug"] for item in CASES])
def test_execute_returns_fixture_in_airgapped_mode(case: dict[str, str]) -> None:
    adapter_cls = _load_adapter_class(case["module_name"], case["class_name"])
    adapter = adapter_cls(mode="airgapped")
    response = adapter.execute({"operation": "mission_training_rollout", "scenario": "contested-airspace"})

    assert response["integration_id"] == case["slug"]
    assert response["domain"] == "simulation"
    assert response["mode"] == "airgapped"
    assert response["source"] == "fixture"
    assert response["request"]["operation"] == "mission_training_rollout"
    assert response["request"]["scenario"] == "contested-airspace"
    assert isinstance(response["result"], dict)
    assert response["result"]


@pytest.mark.parametrize("case", CASES, ids=[item["slug"] for item in CASES])
def test_execute_rejects_non_mapping_params(case: dict[str, str]) -> None:
    adapter_cls = _load_adapter_class(case["module_name"], case["class_name"])
    adapter = adapter_cls(mode="airgapped")
    with pytest.raises(ValueError, match="dictionary"):
        adapter.execute(params=["invalid"])  # type: ignore[arg-type]
