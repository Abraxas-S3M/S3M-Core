"""Tests for dashboard integration wrappers in sovereign airgapped workflows."""

from __future__ import annotations

import importlib
import importlib.util
from pathlib import Path
from typing import Any

import pytest

from packages.integrations.base import IntegrationManifest


REPO_ROOT = Path(__file__).resolve().parents[1]

ADAPTER_CASES: list[dict[str, Any]] = [
    {
        "slug_dir": "battlesimulator",
        "class_name": "BattlesimulatorAdapter",
        "integration_id": "battlesimulator",
        "manifest_name": "BattleSimulator",
        "license": "MIT",
        "source_url": "https://github.com/gregparkes/BattleSimulator",
        "execute_params": {"operation": "status"},
        "response_contract": "fixture_passthrough",
    },
    {
        "slug_dir": "panopticon-ai",
        "class_name": "PanopticonAiAdapter",
        "integration_id": "panopticon-ai",
        "manifest_name": "Panopticon AI",
        "license": "MIT",
        "source_url": "https://github.com/Panopticon-AI-team/panopticon",
        "execute_params": {"operation": "status"},
        "response_contract": "fixture_passthrough",
    },
    {
        "slug_dir": "battleagent",
        "class_name": "BattleagentAdapter",
        "integration_id": "battleagent",
        "manifest_name": "BattleAgent",
        "license": "Apache 2.0",
        "source_url": "https://github.com/agiresearch/BattleAgent",
        "execute_params": {"operation": "status"},
        "response_contract": "fixture_passthrough",
    },
    {
        "slug_dir": "fleetbase",
        "class_name": "FleetbaseAdapter",
        "integration_id": "fleetbase",
        "manifest_name": "Fleetbase",
        "license": "Apache 2.0",
        "source_url": "https://github.com/fleetbase/fleetbase",
        "execute_params": {"operation": "status"},
        "response_contract": "fixture_passthrough",
    },
    {
        "slug_dir": "watcher",
        "class_name": "WatcherAdapter",
        "integration_id": "watcher",
        "manifest_name": "Watcher",
        "license": "Apache 2.0",
        "source_url": "https://github.com/thalesgroup-cert/Watcher",
        "execute_params": {"operation": "status"},
        "response_contract": "fixture_passthrough",
    },
    {
        "slug_dir": "opencti",
        "class_name": "OpenctiAdapter",
        "integration_id": "opencti",
        "manifest_name": "OpenCTI",
        "license": "Apache 2.0",
        "source_url": "https://github.com/OpenCTI-Platform/opencti",
        "execute_params": {"action": "dashboard_summary"},
        "response_contract": "fixture_envelope",
    },
    {
        "slug_dir": "jsbsim",
        "class_name": "JsbsimAdapter",
        "integration_id": "jsbsim",
        "manifest_name": "JSBSim",
        "license": "LGPL-2.1",
        "source_url": "https://github.com/JSBSim-Team/jsbsim",
        "execute_params": {"action": "dashboard_summary"},
        "response_contract": "fixture_envelope",
    },
    {
        "slug_dir": "langfuse",
        "class_name": "LangfuseAdapter",
        "integration_id": "langfuse",
        "manifest_name": "Langfuse",
        "license": "MIT",
        "source_url": "https://github.com/langfuse/langfuse",
        "execute_params": {"action": "dashboard_summary"},
        "response_contract": "fixture_envelope",
    },
    {
        "slug_dir": "evidently",
        "class_name": "EvidentlyAdapter",
        "integration_id": "evidently",
        "manifest_name": "Evidently",
        "license": "Apache 2.0",
        "source_url": "https://github.com/evidentlyai/evidently",
        "execute_params": {"action": "dashboard_summary"},
        "response_contract": "fixture_envelope",
    },
    {
        "slug_dir": "phoenix",
        "class_name": "PhoenixAdapter",
        "integration_id": "phoenix",
        "manifest_name": "Phoenix",
        "license": "Apache 2.0",
        "source_url": "https://github.com/Arize-ai/phoenix",
        "execute_params": {"action": "dashboard_summary"},
        "response_contract": "fixture_envelope",
    },
    {
        "slug_dir": "world-monitor",
        "class_name": "WorldMonitorAdapter",
        "integration_id": "world-monitor",
        "manifest_name": "World Monitor",
        "license": "MIT",
        "source_url": "https://github.com/koala73/worldmonitor",
    },
    {
        "slug_dir": "misp-dashboard",
        "class_name": "MispDashboardAdapter",
        "integration_id": "misp-dashboard",
        "manifest_name": "MISP-Dashboard",
        "license": "AGPL-3.0",
        "source_url": "https://github.com/MISP/misp-dashboard",
    },
    {
        "slug_dir": "streamlit-cybersecurity-dashboard",
        "class_name": "StreamlitCybersecurityDashboardAdapter",
        "integration_id": "streamlit-cybersecurity-dashboard",
        "manifest_name": "Streamlit-Cybersecurity-Dashboard",
        "license": "MIT",
        "source_url": "https://github.com/ajitagupta/streamlit-cybersecurity-dashboard",
    },
    {
        "slug_dir": "supply-chain-management-dashboard",
        "class_name": "SupplyChainManagementDashboardAdapter",
        "integration_id": "supply-chain-management-dashboard",
        "manifest_name": "Supply-Chain-Management-Dashboard",
        "license": "MIT",
        "source_url": "https://github.com/GirishKumarV25/Supply-Chain-Management-Dashboard",
    },
    {
        "slug_dir": "supply-chain-performance-dashboard",
        "class_name": "SupplyChainPerformanceDashboardAdapter",
        "integration_id": "supply-chain-performance-dashboard",
        "manifest_name": "Supply-Chain-Performance-Dashboard",
        "license": "MIT",
        "source_url": "https://github.com/PolinaBurova/Supply-Chain-Performance-Dashboard",
    },
]


def _load_adapter(module_path: str, class_name: str) -> type[Any]:
    module = importlib.import_module(module_path)
    return getattr(module, class_name)


@pytest.mark.parametrize("case", ADAPTER_CASES, ids=[item["integration_id"] for item in ADAPTER_CASES])
def test_manifest_fields(case: dict[str, Any]) -> None:
    adapter_cls = _load_adapter_class(case["slug_dir"], case["class_name"])
    adapter = adapter_cls(mode="airgapped")

    assert isinstance(manifest, IntegrationManifest)
    assert manifest.name == case["manifest_name"]
    assert manifest.slug == case["integration_id"]
    assert manifest.domain == "dashboard"
    assert manifest.license == license_name
    assert manifest.airgapped_support is True
    assert adapter.logger.name == f"s3m.integrations.dashboard.{slug}"


@pytest.mark.parametrize("case", ADAPTER_CASES, ids=[item["integration_id"] for item in ADAPTER_CASES])
def test_validate_availability_airgapped(case: dict[str, Any]) -> None:
    adapter_cls = _load_adapter_class(case["slug_dir"], case["class_name"])
    assert adapter_cls(mode="airgapped").validate_availability() is True


@pytest.mark.parametrize("case", ADAPTER_CASES, ids=[item["integration_id"] for item in ADAPTER_CASES])
def test_execute_uses_fixture_in_airgapped_mode(case: dict[str, Any]) -> None:
    adapter_cls = _load_adapter_class(case["slug_dir"], case["class_name"])
    adapter = adapter_cls(mode="airgapped")

    response = adapter.execute(case["execute_params"])

    assert response["integration_id"] == case["integration_id"]
    assert response["domain"] == "dashboard"
    assert response["mode"] == "airgapped"

    if case["response_contract"] == "fixture_passthrough":
        assert response["request"] == case["execute_params"]
        assert response["status"] == "ok"
    else:
        assert response["source"] == "fixture"
        assert response["action"] == "dashboard_summary"
        assert isinstance(response["result"], dict)
        assert response["result"]


@pytest.mark.parametrize("case", ADAPTER_CASES, ids=[item["integration_id"] for item in ADAPTER_CASES])
def test_execute_rejects_non_mapping_params(case: dict[str, Any]) -> None:
    adapter_cls = _load_adapter_class(case["slug_dir"], case["class_name"])
    adapter = adapter_cls(mode="airgapped")

    with pytest.raises(ValueError, match="mapping|dictionary"):
        adapter.execute(params="invalid")  # type: ignore[arg-type]
