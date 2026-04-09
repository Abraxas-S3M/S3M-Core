"""Tests for cyber integration wrappers in contested environments."""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
CYBER_DIR = ROOT / "packages" / "integrations" / "cyber"

CASES: list[tuple[str, str]] = [
    ("soc-automation-with-automated-response-f", "SocAutomationWithAutomatedAdapter"),
    ("wazuh-suricata", "WazuhSuricataAdapter"),
    ("thehive", "ThehiveAdapter"),
    ("cortex", "CortexAdapter"),
    ("misp", "MispAdapter"),
]


def _load_adapter_class(slug: str, class_name: str):
    adapter_path = CYBER_DIR / slug / "adapter.py"
    module_name = f"tests.dynamic_{slug.replace('-', '_')}_adapter"
    spec = importlib.util.spec_from_file_location(module_name, adapter_path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return getattr(module, class_name)


@pytest.mark.parametrize(("slug", "class_name"), CASES)
def test_adapter_get_manifest_reads_expected_metadata(slug: str, class_name: str) -> None:
    adapter_cls = _load_adapter_class(slug, class_name)
    adapter = adapter_cls(mode="airgapped")

    manifest = adapter.get_manifest()

    assert manifest.slug == slug
    assert manifest.domain == "cyber"
    assert manifest.source_url.startswith("https://github.com/")
    assert manifest.license == "Unknown"
    assert adapter.logger.name == f"s3m.integrations.cyber.{slug}"


@pytest.mark.parametrize(("slug", "class_name"), CASES)
def test_adapter_airgapped_mode_returns_fixture_payload(slug: str, class_name: str) -> None:
    adapter_cls = _load_adapter_class(slug, class_name)
    adapter = adapter_cls(mode="airgapped")

    response = adapter.execute({"action": "tactical_validation"})

    assert response["status"] == "ok"
    assert response["mode"] == "airgapped"
    assert response["integration_id"] == slug
    assert response["request"]["action"] == "tactical_validation"
    assert isinstance(response["result"], dict)
    assert response["result"]


@pytest.mark.parametrize(("slug", "class_name"), CASES)
def test_adapter_validate_availability_uses_airgapped_fixture(slug: str, class_name: str) -> None:
    adapter_cls = _load_adapter_class(slug, class_name)
    adapter = adapter_cls(mode="airgapped")

    assert adapter.validate_availability() is True
