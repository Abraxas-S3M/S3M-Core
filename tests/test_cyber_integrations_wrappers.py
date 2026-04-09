"""Unit tests for cyber integration wrappers.

Military/tactical context:
These tests guarantee predictable adapter behavior for cyber defense modules
deployed on sovereign and disconnected operational infrastructure.
"""

from __future__ import annotations

import importlib

import pytest


ADAPTER_MATRIX = [
    (
        "packages.integrations.cyber.security-onion.adapter",
        "SecurityOnionAdapter",
        "security-onion",
        "https://github.com/Security-Onion-Solutions/security-onion",
    ),
    (
        "packages.integrations.cyber.wazuh-rules.adapter",
        "WazuhRulesAdapter",
        "wazuh-rules",
        "https://github.com/socfortress/Wazuh-Rules",
    ),
    (
        "packages.integrations.cyber.thehive-cortex-misp-docker-compose-lab.adapter",
        "ThehiveCortexMispDockerAdapter",
        "thehive-cortex-misp-docker-compose-lab",
        "https://github.com/ls111-cybersec/thehive-cortex-misp-docker-compose-lab11update",
    ),
    (
        "packages.integrations.cyber.soc-automation-project-with-wazuh-and-th.adapter",
        "SocAutomationProjectWithAdapter",
        "soc-automation-project-with-wazuh-and-th",
        "Search related community forks",
    ),
    (
        "packages.integrations.cyber.awesome-siem.adapter",
        "AwesomeSiemAdapter",
        "awesome-siem",
        "https://github.com/cybersader/awesome-siem",
    ),
]


@pytest.mark.parametrize(("module_path", "class_name", "slug", "source_url"), ADAPTER_MATRIX)
def test_manifest_fields_and_logger_name(module_path: str, class_name: str, slug: str, source_url: str) -> None:
    module = importlib.import_module(module_path)
    adapter_cls = getattr(module, class_name)
    adapter = adapter_cls(mode="airgapped")

    manifest = adapter.get_manifest()
    assert manifest.slug == slug
    assert manifest.domain == "cyber"
    assert manifest.source_url == source_url
    assert manifest.integration_type == "adapter"
    assert adapter.logger.name == f"s3m.integrations.cyber.{slug}"


@pytest.mark.parametrize(("module_path", "class_name", "slug", "_source_url"), ADAPTER_MATRIX)
def test_execute_returns_fixture_in_airgapped_mode(module_path: str, class_name: str, slug: str, _source_url: str) -> None:
    module = importlib.import_module(module_path)
    adapter_cls = getattr(module, class_name)
    adapter = adapter_cls(mode="airgapped")

    output = adapter.execute({"operation": "status"})

    assert output["integration_id"] == slug
    assert output["mode"] == "airgapped"
    assert output["source"] == "fixture"
    assert isinstance(output["data"], dict)
    assert output["data"].get("status") == "ok"


@pytest.mark.parametrize(("module_path", "class_name", "_slug", "_source_url"), ADAPTER_MATRIX)
def test_validate_availability_returns_bool(module_path: str, class_name: str, _slug: str, _source_url: str) -> None:
    module = importlib.import_module(module_path)
    adapter_cls = getattr(module, class_name)
    adapter = adapter_cls(mode="online")

    assert isinstance(adapter.validate_availability(), bool)


@pytest.mark.parametrize(("module_path", "class_name", "_slug", "_source_url"), ADAPTER_MATRIX)
def test_execute_rejects_invalid_params(module_path: str, class_name: str, _slug: str, _source_url: str) -> None:
    module = importlib.import_module(module_path)
    adapter_cls = getattr(module, class_name)
    adapter = adapter_cls(mode="airgapped")

    with pytest.raises(ValueError):
        adapter.execute(params=["not", "a", "dict"])  # type: ignore[arg-type]
