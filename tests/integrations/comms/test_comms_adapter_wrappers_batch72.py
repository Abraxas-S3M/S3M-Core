"""Unit tests for comms-domain integration wrappers.

Military/tactical context:
These tests confirm deterministic airgapped behavior for secure
communications adapters used in disconnected field operations.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path
from typing import Any

import pytest
import yaml

from packages.integrations.base import IntegrationManifest
from packages.integrations.registry import discover_integration_manifests


ROOT = Path(__file__).resolve().parents[3]
COMMS_DIR = ROOT / "packages" / "integrations" / "comms"

CASES: list[tuple[str, str, str, str, str, str]] = [
    (
        "ninja",
        "NinjaAdapter",
        "Ninja",
        "https://github.com/ahmedkhlief/Ninja",
        "session_health_check",
        "result",
    ),
    (
        "wsc2",
        "Wsc2Adapter",
        "WSC2",
        "https://github.com/Arno0x/WSC2",
        "route_status",
        "result",
    ),
    (
        "talkkonnect",
        "TalkkonnectAdapter",
        "talkkonnect",
        "https://github.com/talkkonnect/talkkonnect",
        "ptt_channel_readiness",
        "result",
    ),
    (
        "covert-c2",
        "CovertC2Adapter",
        "Covert-C2",
        "https://github.com/efchatz/Covert-C2",
        "covert_route_audit",
        "result",
    ),
    (
        "ejabberd",
        "EjabberdAdapter",
        "ejabberd",
        "https://github.com/processone/ejabberd",
        "xmpp_fabric_status",
        "result",
    ),
]


def _load_adapter_class(slug: str, class_name: str) -> tuple[type[Any], Any]:
    adapter_path = COMMS_DIR / slug / "adapter.py"
    module_name = f"tests.dynamic_comms_{slug.replace('-', '_')}_adapter"
    spec = importlib.util.spec_from_file_location(module_name, adapter_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return getattr(module, class_name), module


@pytest.mark.parametrize(
    ("slug", "class_name", "expected_name", "expected_source_url", "_operation", "_result_key"),
    CASES,
)
def test_manifest_fields_and_logger_name(
    slug: str,
    class_name: str,
    expected_name: str,
    expected_source_url: str,
    _operation: str,
    _result_key: str,
) -> None:
    adapter_cls, _module = _load_adapter_class(slug, class_name)
    adapter = adapter_cls(mode="airgapped")
    manifest = adapter.get_manifest()

    manifest_yaml = COMMS_DIR / slug / "manifest.yaml"
    raw = yaml.safe_load(manifest_yaml.read_text(encoding="utf-8"))

    assert isinstance(manifest, IntegrationManifest)
    assert manifest.name == expected_name
    assert manifest.name == raw["name"]
    assert manifest.slug == slug
    assert manifest.domain == "comms"
    assert manifest.source_url == expected_source_url
    assert manifest.license == "Unknown"
    assert manifest.integration_type == "adapter"
    assert manifest.airgapped_support is True
    assert adapter.logger.name == f"s3m.integrations.comms.{slug}"


@pytest.mark.parametrize(
    ("slug", "class_name", "_expected_name", "_expected_source_url", "_operation", "_result_key"),
    CASES,
)
def test_validate_availability_in_airgapped_mode(
    slug: str,
    class_name: str,
    _expected_name: str,
    _expected_source_url: str,
    _operation: str,
    _result_key: str,
) -> None:
    adapter_cls, _module = _load_adapter_class(slug, class_name)
    adapter = adapter_cls(mode="airgapped")
    assert adapter.validate_availability() is True


@pytest.mark.parametrize(
    ("slug", "class_name", "_expected_name", "_expected_source_url", "operation", "result_key"),
    CASES,
)
def test_execute_returns_fixture_payload_in_airgapped_mode(
    slug: str,
    class_name: str,
    _expected_name: str,
    _expected_source_url: str,
    operation: str,
    result_key: str,
) -> None:
    adapter_cls, _module = _load_adapter_class(slug, class_name)
    adapter = adapter_cls(mode="airgapped")
    output = adapter.execute({"operation": operation, "priority": "high"})

    assert output["integration_id"] == slug
    assert output["domain"] == "comms"
    assert output["mode"] == "airgapped"
    assert output["source"] == "fixture"
    assert output["status"] == "ok"
    assert output["operation"] == operation
    assert output["request"]["priority"] == "high"
    assert isinstance(output[result_key], dict)
    assert output[result_key]


@pytest.mark.parametrize(
    ("slug", "class_name", "_expected_name", "_expected_source_url", "_operation", "_result_key"),
    CASES,
)
def test_validate_availability_online_uses_cli_probe(
    slug: str,
    class_name: str,
    _expected_name: str,
    _expected_source_url: str,
    _operation: str,
    _result_key: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    adapter_cls, module = _load_adapter_class(slug, class_name)
    monkeypatch.setattr(module.shutil, "which", lambda _cmd: "/usr/bin/mock-tool")
    adapter = adapter_cls(mode="online")
    assert adapter.validate_availability() is True


@pytest.mark.parametrize(
    ("slug", "class_name", "_expected_name", "_expected_source_url", "_operation", "_result_key"),
    CASES,
)
def test_execute_rejects_invalid_params(
    slug: str,
    class_name: str,
    _expected_name: str,
    _expected_source_url: str,
    _operation: str,
    _result_key: str,
) -> None:
    adapter_cls, _module = _load_adapter_class(slug, class_name)
    adapter = adapter_cls(mode="airgapped")
    with pytest.raises(ValueError, match="dictionary"):
        adapter.execute(["invalid"])  # type: ignore[arg-type]


def test_comms_manifests_are_discoverable() -> None:
    manifests = discover_integration_manifests(ROOT / "packages" / "integrations")
    comms_slugs = {manifest.slug for manifest in manifests if manifest.domain == "comms"}
    assert {"ninja", "wsc2", "talkkonnect", "covert-c2", "ejabberd"}.issubset(comms_slugs)
