from __future__ import annotations

import importlib

import pytest


def _load():
    module = importlib.import_module("packages.integrations.cyber.incident-response-plan-template.adapter")
    return module.IncidentResponsePlanTemplateAdapter, module


def test_manifest_is_loaded_from_yaml() -> None:
    adapter_class, _ = _load()
    manifest = adapter_class(mode="airgapped").get_manifest()
    assert manifest.slug == "incident-response-plan-template"
    assert manifest.domain == "cyber"
    assert manifest.source_url == "https://github.com/counteractive/incident-response-plan-template"


def test_logger_name_matches_required_pattern() -> None:
    adapter_class, _ = _load()
    adapter = adapter_class(mode="airgapped")
    assert adapter.logger.name == "s3m.integrations.cyber.incident-response-plan-template"


def test_validate_availability_airgapped_uses_fixture() -> None:
    adapter_class, _ = _load()
    assert adapter_class(mode="airgapped").validate_availability() is True


def test_validate_availability_online_checks_installed_tool(monkeypatch) -> None:
    adapter_class, module = _load()
    monkeypatch.setattr(module.shutil, "which", lambda _cmd: "/usr/bin/mock-tool")
    assert adapter_class(mode="online").validate_availability() is True


def test_execute_airgapped_returns_fixture_payload() -> None:
    adapter_class, _ = _load()
    output = adapter_class(mode="airgapped").execute({"operation": "generate_checklist"})
    assert output["source"] == "fixture"
    assert output["result"]["template_set"] == "counteractive-ir-plan"


def test_execute_rejects_invalid_params() -> None:
    adapter_class, _ = _load()
    adapter = adapter_class(mode="airgapped")
    with pytest.raises(ValueError):
        adapter.execute("invalid")  # type: ignore[arg-type]
    with pytest.raises(ValueError):
        adapter.execute({"operation": "unsupported"})
