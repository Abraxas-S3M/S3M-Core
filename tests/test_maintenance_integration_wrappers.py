"""Unit tests for maintenance integration wrappers.

Military/tactical context:
These tests ensure maintenance adapters keep deterministic airgapped behavior
for sovereign sustainment operations when external links are unavailable.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path
from typing import Any

import pytest


REPO_ROOT = Path(__file__).resolve().parents[1]
MAINTENANCE_DIR = REPO_ROOT / "packages" / "integrations" / "maintenance"

CASES: list[dict[str, str]] = [
    {
        "slug": "dolibarr-dolibarr",
        "class_name": "DolibarrdolibarrAdapter",
        "manifest_name": "dolibarr/dolibarr",
        "source_url": "https://github.com/dolibarr/dolibarr",
        "license": "Unknown",
    },
    {
        "slug": "orangehrm-orangehrm",
        "class_name": "OrangehrmorangehrmAdapter",
        "manifest_name": "orangehrm/orangehrm",
        "source_url": "https://github.com/orangehrm/orangehrm",
        "license": "Unknown",
    },
    {
        "slug": "nocobase-nocobase",
        "class_name": "NocobasenocobaseAdapter",
        "manifest_name": "nocobase/nocobase",
        "source_url": "https://github.com/nocobase/nocobase",
        "license": "Unknown",
    },
]


def _load_adapter_class(slug: str, class_name: str) -> type[Any]:
    adapter_path = MAINTENANCE_DIR / slug / "adapter.py"
    module_name = f"tests.dynamic_maintenance_{slug.replace('-', '_')}_adapter"
    spec = importlib.util.spec_from_file_location(module_name, adapter_path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return getattr(module, class_name)


@pytest.mark.parametrize("entry", CASES, ids=[item["slug"] for item in CASES])
def test_maintenance_wrapper_manifest_fields(entry: dict[str, str]) -> None:
    adapter_cls = _load_adapter_class(entry["slug"], entry["class_name"])
    adapter = adapter_cls(mode="airgapped")

    manifest = adapter.get_manifest()
    assert manifest.name == entry["manifest_name"]
    assert manifest.slug == entry["slug"]
    assert manifest.domain == "maintenance"
    assert manifest.source_url == entry["source_url"]
    assert manifest.license == entry["license"]
    assert manifest.integration_type == "adapter"
    assert manifest.airgapped_support is True
    assert adapter.logger.name == f"s3m.integrations.maintenance.{entry['slug']}"


@pytest.mark.parametrize("entry", CASES, ids=[item["slug"] for item in CASES])
def test_maintenance_wrapper_validate_availability_in_airgapped(entry: dict[str, str]) -> None:
    adapter_cls = _load_adapter_class(entry["slug"], entry["class_name"])
    adapter = adapter_cls(mode="airgapped")
    assert adapter.validate_availability() is True


@pytest.mark.parametrize("entry", CASES, ids=[item["slug"] for item in CASES])
def test_maintenance_wrapper_execute_returns_fixture(entry: dict[str, str]) -> None:
    adapter_cls = _load_adapter_class(entry["slug"], entry["class_name"])
    adapter = adapter_cls(mode="airgapped")

    response = adapter.execute({"operation": "status"})
    assert response["integration_id"] == entry["slug"]
    assert response["domain"] == "maintenance"
    assert response["mode"] == "airgapped"
    assert response["source"] == "fixture"
    assert response["status"] == "ok"
    assert response["operation"] == "status"
    assert response["request"]["operation"] == "status"
    assert isinstance(response["result"], dict)
    assert response["result"]


@pytest.mark.parametrize("entry", CASES, ids=[item["slug"] for item in CASES])
def test_maintenance_wrapper_execute_rejects_non_mapping(entry: dict[str, str]) -> None:
    adapter_cls = _load_adapter_class(entry["slug"], entry["class_name"])
    adapter = adapter_cls(mode="airgapped")

    with pytest.raises(ValueError, match="dictionary"):
        adapter.execute(params="invalid")  # type: ignore[arg-type]
