"""Tests for dataset integration wrappers in sovereign offline environments."""

from __future__ import annotations

import importlib.util
from pathlib import Path
from typing import Any

import pytest


REPO_ROOT = Path(__file__).resolve().parents[1]
DATASETS_DIR = REPO_ROOT / "packages" / "integrations" / "datasets"

DATASET_CASES: list[dict[str, str]] = [
    {
        "slug": "military-target-&-equipment-detection",
        "class_name": "MilitaryTargetEquipmentAdapter",
        "name": "Military Target & Equipment Detection",
        "source_url": "https://github.com/KarthikPrabhu2541/Military-Target-and-Equipment-Detection",
        "license": "MIT (repo); dataset ",
    },
    {
        "slug": "vehicledetection-sar-small-object",
        "class_name": "VehicledetectionsarSmallObjectAdapter",
        "name": "VehicleDetection (SAR Small Object)",
        "source_url": "https://github.com/KK-MUT/VehicleDetection",
        "license": "Request from authors",
    },
    {
        "slug": "open-transport-data",
        "class_name": "OpenTransportDataAdapter",
        "name": "Open Transport Data",
        "source_url": "https://github.com/ITSLeeds/opentransportdata",
        "license": "Various",
    },
    {
        "slug": "panopticon-ai-scenarios",
        "class_name": "PanopticonAiScenariosAdapter",
        "name": "Panopticon AI Scenarios",
        "source_url": "https://github.com/Panopticon-AI-team/panopticon",
        "license": "MIT",
    },
]


def _load_adapter_class(slug: str, class_name: str) -> type[Any]:
    adapter_path = DATASETS_DIR / slug / "adapter.py"
    module_name = f"tests.dynamic_{slug.replace('-', '_').replace('&', 'and')}_adapter"
    spec = importlib.util.spec_from_file_location(module_name, adapter_path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return getattr(module, class_name)


@pytest.mark.parametrize("entry", DATASET_CASES, ids=[item["slug"] for item in DATASET_CASES])
def test_dataset_wrapper_manifest_fields(entry: dict[str, str]) -> None:
    adapter_cls = _load_adapter_class(entry["slug"], entry["class_name"])
    adapter = adapter_cls(mode="airgapped")

    manifest = adapter.get_manifest()
    assert manifest.name == entry["name"]
    assert manifest.slug == entry["slug"]
    assert manifest.domain == "datasets"
    assert manifest.source_url == entry["source_url"]
    assert manifest.license == entry["license"]
    assert manifest.airgapped_support is True
    assert adapter.logger.name == f"s3m.integrations.datasets.{entry['slug']}"


@pytest.mark.parametrize("entry", DATASET_CASES, ids=[item["slug"] for item in DATASET_CASES])
def test_dataset_wrapper_airgapped_execution(entry: dict[str, str]) -> None:
    adapter_cls = _load_adapter_class(entry["slug"], entry["class_name"])
    adapter = adapter_cls(mode="airgapped")

    assert adapter.validate_availability() is True

    response = adapter.execute({"action": "unit-test"})
    assert response["status"] == "ok"
    assert response["mode"] == "airgapped"
    assert response["integration_id"] == entry["slug"]
    assert response["domain"] == "datasets"
    assert response["source"] == "fixture"
    assert response["request"]["action"] == "unit-test"
    assert isinstance(response["result"], dict)
    assert response["result"]


@pytest.mark.parametrize("entry", DATASET_CASES, ids=[item["slug"] for item in DATASET_CASES])
def test_dataset_wrapper_execute_rejects_non_mapping(entry: dict[str, str]) -> None:
    adapter_cls = _load_adapter_class(entry["slug"], entry["class_name"])
    adapter = adapter_cls(mode="airgapped")

    with pytest.raises(ValueError, match="dictionary"):
        adapter.execute(params="invalid")  # type: ignore[arg-type]
