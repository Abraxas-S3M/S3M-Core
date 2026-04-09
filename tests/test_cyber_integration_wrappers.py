"""Unit tests for cyber-domain integration wrappers.

Military/tactical context:
These tests guarantee that incident-response wrappers remain deterministic in
airgapped deployments where live internet access is unavailable.
"""

from __future__ import annotations

import importlib

import pytest

from packages.integrations.base import IntegrationManifest


ADAPTER_CASES = [
    (
        "packages.integrations.cyber.playbooks.adapter",
        "PlaybooksAdapter",
        "playbooks",
        "Playbooks",
    ),
    (
        "packages.integrations.cyber.incident-playbook.adapter",
        "IncidentPlaybookAdapter",
        "incident-playbook",
        "Incident-Playbook",
    ),
    (
        "packages.integrations.cyber.awesome-incident-response.adapter",
        "AwesomeIncidentResponseAdapter",
        "awesome-incident-response",
        "awesome-incident-response",
    ),
    (
        "packages.integrations.cyber.gsvsoc-cirt-playbook-battle-cards.adapter",
        "GsvsocCirtPlaybookBattleAdapter",
        "gsvsoc-cirt-playbook-battle-cards",
        "gsvsoc_cirt-playbook-battle-cards",
    ),
    (
        "packages.integrations.cyber.soc-multitool.adapter",
        "SocMultitoolAdapter",
        "soc-multitool",
        "SOC-Multitool",
    ),
]


def _load_adapter(module_path: str, class_name: str):
    module = importlib.import_module(module_path)
    return getattr(module, class_name)


@pytest.mark.parametrize(("module_path", "class_name", "slug", "expected_name"), ADAPTER_CASES)
def test_manifest_loaded_from_yaml(module_path: str, class_name: str, slug: str, expected_name: str) -> None:
    adapter_cls = _load_adapter(module_path, class_name)
    adapter = adapter_cls(mode="airgapped")
    manifest = adapter.get_manifest()
    assert isinstance(manifest, IntegrationManifest)
    assert manifest.name == expected_name
    assert manifest.slug == slug
    assert manifest.domain == "cyber"
    assert manifest.source_url.startswith("https://github.com/")
    assert manifest.license == "Unknown"


@pytest.mark.parametrize(("module_path", "class_name", "slug", "_expected_name"), ADAPTER_CASES)
def test_logger_name_uses_required_namespace(
    module_path: str, class_name: str, slug: str, _expected_name: str
) -> None:
    adapter_cls = _load_adapter(module_path, class_name)
    adapter = adapter_cls(mode="airgapped")
    assert adapter.logger.name == f"s3m.integrations.cyber.{slug}"


@pytest.mark.parametrize(("module_path", "class_name", "_slug", "_expected_name"), ADAPTER_CASES)
def test_validate_availability_succeeds_in_airgapped_mode(
    module_path: str, class_name: str, _slug: str, _expected_name: str
) -> None:
    adapter_cls = _load_adapter(module_path, class_name)
    adapter = adapter_cls(mode="airgapped")
    assert adapter.validate_availability() is True


@pytest.mark.parametrize(("module_path", "class_name", "slug", "_expected_name"), ADAPTER_CASES)
def test_execute_returns_fixture_entries_in_airgapped_mode(
    module_path: str, class_name: str, slug: str, _expected_name: str
) -> None:
    adapter_cls = _load_adapter(module_path, class_name)
    adapter = adapter_cls(mode="airgapped")
    output = adapter.execute({"limit": 2})
    assert output["mode"] == "airgapped"
    assert output["integration_id"] == slug
    assert output["returned"] <= 2
    assert isinstance(output["entries"], list)
    assert output["entries"]


@pytest.mark.parametrize(("module_path", "class_name", "_slug", "_expected_name"), ADAPTER_CASES)
def test_execute_rejects_invalid_params_type(
    module_path: str, class_name: str, _slug: str, _expected_name: str
) -> None:
    adapter_cls = _load_adapter(module_path, class_name)
    adapter = adapter_cls(mode="airgapped")
    output = adapter.execute("not-a-dict")  # type: ignore[arg-type]
    assert output["status"] == "error"
    assert output["error"] == "invalid_params"


@pytest.mark.parametrize(("module_path", "class_name", "_slug", "_expected_name"), ADAPTER_CASES)
def test_execute_rejects_invalid_limit_range(
    module_path: str, class_name: str, _slug: str, _expected_name: str
) -> None:
    adapter_cls = _load_adapter(module_path, class_name)
    adapter = adapter_cls(mode="airgapped")
    output = adapter.execute({"limit": 0})
    assert output["status"] == "error"
    assert output["error"] == "invalid_limit_range"

