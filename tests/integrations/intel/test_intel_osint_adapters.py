"""Unit tests for intel OSINT integration adapters.

Military/tactical context:
These tests enforce deterministic wrapper behavior for intelligence briefings
executed on sovereign and disconnected mission infrastructure.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path
from typing import Any

import pytest


ROOT = Path(__file__).resolve().parents[3]
INTEL_DIR = ROOT / "packages" / "integrations" / "intel"

CASES: list[tuple[str, str, str, str]] = [
    (
        "osint-framework",
        "OsintFrameworkAdapter",
        "osint-framework",
        "https://github.com/fr4nc1stein/osint-framework",
    ),
    (
        "tigmint",
        "TigmintAdapter",
        "TIGMINT",
        "https://github.com/TIGMINT/TIGMINT",
    ),
    (
        "metaosint",
        "MetaosintAdapter",
        "MetaOSINT",
        "https://github.com/MetaOSINT (related)",
    ),
    (
        "osint",
        "OsintAdapter",
        "osint",
        "https://github.com/doctorfree/osint",
    ),
    (
        "aegis",
        "AegisAdapter",
        "AEGIS",
        "https://github.com/alex-armand-blumberg/AEGIS",
    ),
]


def _load_adapter_class(slug: str, class_name: str) -> type[Any]:
    adapter_path = INTEL_DIR / slug / "adapter.py"
    module_name = f"tests.dynamic_intel_{slug.replace('-', '_')}_adapter"
    spec = importlib.util.spec_from_file_location(module_name, adapter_path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return getattr(module, class_name)


@pytest.mark.parametrize(("slug", "class_name", "name", "source_url"), CASES)
def test_manifest_and_logger_fields(
    slug: str,
    class_name: str,
    name: str,
    source_url: str,
) -> None:
    adapter_cls = _load_adapter_class(slug, class_name)
    adapter = adapter_cls(mode="airgapped")

    manifest = adapter.get_manifest()

    assert manifest.name == name
    assert manifest.slug == slug
    assert manifest.domain == "intel"
    assert manifest.source_url == source_url
    assert manifest.license == "Unknown"
    assert manifest.integration_type == "adapter"
    assert adapter.logger.name == f"s3m.integrations.intel.{slug}"


@pytest.mark.parametrize(("slug", "class_name", "_name", "_source_url"), CASES)
def test_execute_returns_fixture_payload_in_airgapped_mode(
    slug: str,
    class_name: str,
    _name: str,
    _source_url: str,
) -> None:
    adapter_cls = _load_adapter_class(slug, class_name)
    adapter = adapter_cls(mode="airgapped")

    output = adapter.execute({"operation": "briefing_summary"})

    assert output["integration_id"] == slug
    assert output["domain"] == "intel"
    assert output["mode"] == "airgapped"
    assert output["status"] == "ok"
    assert output["source"] == "fixture"
    assert output["operation"] == "briefing_summary"
    assert isinstance(output["result"], dict)
    assert output["result"]


@pytest.mark.parametrize(("slug", "class_name", "_name", "_source_url"), CASES)
def test_validate_availability_uses_fixture_in_airgapped_mode(
    slug: str,
    class_name: str,
    _name: str,
    _source_url: str,
) -> None:
    adapter_cls = _load_adapter_class(slug, class_name)
    adapter = adapter_cls(mode="airgapped")
    assert adapter.validate_availability() is True


@pytest.mark.parametrize(("slug", "class_name", "_name", "_source_url"), CASES)
def test_validate_availability_returns_boolean_online(
    slug: str,
    class_name: str,
    _name: str,
    _source_url: str,
) -> None:
    adapter_cls = _load_adapter_class(slug, class_name)
    adapter = adapter_cls(mode="online")
    assert isinstance(adapter.validate_availability(), bool)


@pytest.mark.parametrize(("slug", "class_name", "_name", "_source_url"), CASES)
def test_execute_rejects_invalid_params(
    slug: str,
    class_name: str,
    _name: str,
    _source_url: str,
) -> None:
    adapter_cls = _load_adapter_class(slug, class_name)
    adapter = adapter_cls(mode="airgapped")
    with pytest.raises(ValueError):
        adapter.execute(["not", "a", "mapping"])  # type: ignore[arg-type]


@pytest.mark.parametrize(("slug", "class_name", "_name", "_source_url"), CASES)
def test_execute_rejects_unsupported_operation(
    slug: str,
    class_name: str,
    _name: str,
    _source_url: str,
) -> None:
    adapter_cls = _load_adapter_class(slug, class_name)
    adapter = adapter_cls(mode="airgapped")
    with pytest.raises(ValueError):
        adapter.execute({"operation": "unsupported"})

