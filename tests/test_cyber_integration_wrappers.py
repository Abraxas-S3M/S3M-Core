"""Unit tests for cyber-domain integration adapters.

Military/tactical context:
These checks ensure SOC wrapper behavior remains deterministic under
airgapped conditions used by forward and sovereign cyber defense cells.
"""

from __future__ import annotations

import importlib
from pathlib import Path

import pytest


def _load_cyberthreatintelligence_adapter():
    module = importlib.import_module("packages.integrations.cyber.cyberthreatintelligence.adapter")
    return module.CyberthreatintelligenceAdapter


def _load_soc_multitool_extensions_adapter():
    module = importlib.import_module("packages.integrations.cyber.soc-multitool-extensions.adapter")
    return module.SocMultitoolExtensionsAdapter


def test_cyberthreatintelligence_manifest_and_logger_contract() -> None:
    adapter_cls = _load_cyberthreatintelligence_adapter()
    adapter = adapter_cls(mode="airgapped")
    manifest = adapter.get_manifest()

    assert manifest.name == "CyberThreatIntelligence"
    assert manifest.slug == "cyberthreatintelligence"
    assert manifest.domain == "cyber"
    assert adapter.logger.name == "s3m.integrations.cyber.cyberthreatintelligence"


def test_cyberthreatintelligence_airgapped_execute_uses_fixture_limit() -> None:
    adapter_cls = _load_cyberthreatintelligence_adapter()
    adapter = adapter_cls(mode="airgapped")

    result = adapter.execute({"view": "dashboard", "limit": 2})
    assert result["mode"] == "airgapped"
    assert result["requested_view"] == "dashboard"
    assert len(result["priority_indicators"]) == 2


def test_cyberthreatintelligence_online_unavailable_when_no_path_or_binary(monkeypatch) -> None:
    adapter_cls = _load_cyberthreatintelligence_adapter()
    monkeypatch.setenv("PATH", "")
    monkeypatch.setenv("CYBERTHREATINTELLIGENCE_PATH", "/tmp/does-not-exist-cti")
    monkeypatch.delenv("S3M_CYBERTHREATINTELLIGENCE_PATH", raising=False)
    adapter = adapter_cls(mode="online")

    assert adapter.validate_availability() is False


def test_soc_multitool_extensions_manifest_and_logger_contract() -> None:
    adapter_cls = _load_soc_multitool_extensions_adapter()
    adapter = adapter_cls(mode="airgapped")
    manifest = adapter.get_manifest()

    assert manifest.name == "SOC-Multitool extensions"
    assert manifest.slug == "soc-multitool-extensions"
    assert manifest.domain == "cyber"
    assert adapter.logger.name == "s3m.integrations.cyber.soc-multitool-extensions"


def test_soc_multitool_extensions_airgapped_execute_uses_fixture_limit() -> None:
    adapter_cls = _load_soc_multitool_extensions_adapter()
    adapter = adapter_cls(mode="airgapped")

    result = adapter.execute({"workflow": "investigation_assist", "case_id": "SOC-2026-1001", "limit": 1})
    assert result["mode"] == "airgapped"
    assert result["workflow"] == "investigation_assist"
    assert result["case_id"] == "SOC-2026-1001"
    assert len(result["artifacts"]) == 1


def test_soc_multitool_extensions_online_unavailable_when_no_path_or_binary(monkeypatch) -> None:
    adapter_cls = _load_soc_multitool_extensions_adapter()
    monkeypatch.setenv("PATH", "")
    monkeypatch.setenv("SOC_MULTITOOL_EXTENSIONS_PATH", "/tmp/does-not-exist-soc-multitool")
    monkeypatch.delenv("S3M_SOC_MULTITOOL_EXTENSIONS_PATH", raising=False)
    adapter = adapter_cls(mode="online")

    assert adapter.validate_availability() is False


def test_execute_rejects_invalid_limit_values() -> None:
    cti_cls = _load_cyberthreatintelligence_adapter()
    soc_cls = _load_soc_multitool_extensions_adapter()
    cti_adapter = cti_cls(mode="airgapped")
    soc_adapter = soc_cls(mode="airgapped")

    for adapter in (cti_adapter, soc_adapter):
        with pytest.raises(ValueError):
            adapter.execute({"limit": 0})


def test_fixture_files_exist_for_airgapped_support() -> None:
    root = Path(__file__).resolve().parents[1]
    assert (root / "packages/integrations/cyber/cyberthreatintelligence/fixtures/sample_response.json").exists()
    assert (root / "packages/integrations/cyber/soc-multitool-extensions/fixtures/sample_response.json").exists()
