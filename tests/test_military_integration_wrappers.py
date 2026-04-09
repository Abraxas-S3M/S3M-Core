"""Unit tests for military integration wrappers.

Military/tactical context:
These tests verify wrappers remain deterministic in airgapped mode so mission
operators can rehearse cyber and simulation workflows without external services.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path
from typing import Any

import pytest

from packages.integrations.base import IntegrationManifest


ROOT = Path(__file__).resolve().parents[1]
MILITARY_DIR = ROOT / "packages" / "integrations" / "military"

CASES: list[dict[str, str]] = [
    {
        "slug": "malcolm",
        "class_name": "MalcolmAdapter",
        "name": "Malcolm",
        "source_url": "https://github.com/cisagov/Malcolm",
        "license": "AGPL-3.0",
    },
    {
        "slug": "battle-management-language-bml",
        "class_name": "BattleManagementLanguagebmlAdapter",
        "name": "Battle Management Language (BML)",
        "source_url": "https://github.com/c5i-gmu",
        "license": "Apache 2.0",
    },
    {
        "slug": "open-dis",
        "class_name": "OpenDisAdapter",
        "name": "Open-DIS",
        "source_url": "https://github.com/open-dis",
        "license": "BSD-3-Clause",
    },
    {
        "slug": "awesome-security",
        "class_name": "AwesomeSecurityAdapter",
        "name": "awesome-security",
        "source_url": "https://github.com/sbilly/awesome-security",
        "license": "MIT",
    },
    {
        "slug": "openvas",
        "class_name": "OpenvasAdapter",
        "name": "OpenVAS",
        "source_url": "https://github.com/greenbone/openvas-scanner",
        "license": "GPL-2.0",
    },
]


def _load_adapter_class(slug: str, class_name: str) -> type[Any]:
    adapter_path = MILITARY_DIR / slug / "adapter.py"
    module_name = f"tests.dynamic_military_{slug.replace('-', '_')}_adapter"
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

    assert isinstance(manifest, IntegrationManifest)
    assert manifest.name == case["name"]
    assert manifest.slug == case["slug"]
    assert manifest.domain == "military"
    assert manifest.source_url == case["source_url"]
    assert manifest.license == case["license"]
    assert manifest.airgapped_support is True
    assert adapter.logger.name == f"s3m.integrations.military.{case['slug']}"


@pytest.mark.parametrize("case", CASES, ids=[item["slug"] for item in CASES])
def test_validate_availability_in_airgapped_mode(case: dict[str, str]) -> None:
    adapter_cls = _load_adapter_class(case["slug"], case["class_name"])
    adapter = adapter_cls(mode="airgapped")
    assert adapter.validate_availability() is True


@pytest.mark.parametrize("case", CASES, ids=[item["slug"] for item in CASES])
def test_execute_returns_fixture_in_airgapped_mode(case: dict[str, str]) -> None:
    adapter_cls = _load_adapter_class(case["slug"], case["class_name"])
    adapter = adapter_cls(mode="airgapped")

    response = adapter.execute({"operation": "status_check", "priority": "high"})

    assert response["integration_id"] == case["slug"]
    assert response["domain"] == "military"
    assert response["mode"] == "airgapped"
    assert response["source"] == "fixture"
    assert response["status"] == "ok"
    assert response["request"]["operation"] == "status_check"
    assert response["request"]["priority"] == "high"
    assert isinstance(response["result"], dict)
    assert response["result"]


@pytest.mark.parametrize("case", CASES, ids=[item["slug"] for item in CASES])
def test_execute_rejects_non_mapping_params(case: dict[str, str]) -> None:
    adapter_cls = _load_adapter_class(case["slug"], case["class_name"])
    adapter = adapter_cls(mode="airgapped")
    with pytest.raises(ValueError, match="dictionary"):
        adapter.execute(params=["invalid"])  # type: ignore[arg-type]
