"""Tests for dashboard integration wrappers in sovereign airgapped workflows."""

from __future__ import annotations

import importlib
import importlib.util
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[1]

ADAPTER_CASES = [
    {
        "slug_dir": "battlesimulator",
        "class_name": "BattlesimulatorAdapter",
        "integration_id": "battlesimulator",
        "manifest_name": "BattleSimulator",
        "license": "MIT",
        "source_url": "https://github.com/gregparkes/BattleSimulator",
    },
    {
        "slug_dir": "panopticon-ai",
        "class_name": "PanopticonAiAdapter",
        "integration_id": "panopticon-ai",
        "manifest_name": "Panopticon AI",
        "license": "MIT",
        "source_url": "https://github.com/Panopticon-AI-team/panopticon",
    },
    {
        "slug_dir": "battleagent",
        "class_name": "BattleagentAdapter",
        "integration_id": "battleagent",
        "manifest_name": "BattleAgent",
        "license": "Apache 2.0",
        "source_url": "https://github.com/agiresearch/BattleAgent",
    },
    {
        "slug_dir": "fleetbase",
        "class_name": "FleetbaseAdapter",
        "integration_id": "fleetbase",
        "manifest_name": "Fleetbase",
        "license": "Apache 2.0",
        "source_url": "https://github.com/fleetbase/fleetbase",
    },
    {
        "slug_dir": "watcher",
        "class_name": "WatcherAdapter",
        "integration_id": "watcher",
        "manifest_name": "Watcher",
        "license": "Apache 2.0",
        "source_url": "https://github.com/thalesgroup-cert/Watcher",
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
def test_package_exports_expected_adapter(case: dict[str, str]) -> None:
    package = importlib.import_module(f"packages.integrations.dashboard.{case['slug_dir']}")
    assert hasattr(package, case["class_name"])


@pytest.mark.parametrize("case", ADAPTER_CASES, ids=[item["integration_id"] for item in ADAPTER_CASES])
def test_manifest_fields(case: dict[str, str]) -> None:
    adapter_cls = _load_adapter_class(case["slug_dir"], case["class_name"])
    adapter = adapter_cls(mode="airgapped")

    manifest = adapter.get_manifest()
    assert manifest.slug == slug
    assert manifest.domain == "dashboard"
    assert manifest.license == license_name
    assert manifest.airgapped_support is True
    assert adapter.logger.name == f"s3m.integrations.dashboard.{slug}"


@pytest.mark.parametrize(("module_path", "class_name", "slug", "_license_name"), CASES)
def test_execute_airgapped_returns_fixture_data(
    module_path: str,
    class_name: str,
    slug: str,
    _license_name: str,
) -> None:
    adapter_cls = _load_adapter(module_path, class_name)
    adapter = adapter_cls(mode="airgapped")

    response = adapter.execute({"operation": "status"})

    assert response["integration_id"] == case["integration_id"]
    assert response["domain"] == "dashboard"
    assert response["mode"] == "airgapped"
    assert isinstance(response.get("operation"), str)
    if "request" in response:
        assert response["request"] == {"operation": "status"}
    if "source" in response:
        assert response["source"] == "fixture"
    if "data" in response:
        assert isinstance(response["data"], dict)
        assert response["data"]

    # Tactical contract: logger namespace must align to integration slug.
    assert adapter.logger.name == f"s3m.integrations.dashboard.{case['integration_id']}"

@pytest.mark.parametrize("case", ADAPTER_CASES, ids=[item["integration_id"] for item in ADAPTER_CASES])
def test_execute_rejects_non_mapping_params(case: dict[str, str]) -> None:
    adapter_cls = _load_adapter_class(case["slug_dir"], case["class_name"])
    adapter = adapter_cls(mode="airgapped")

    with pytest.raises((TypeError, ValueError), match="dictionary|str"):
        adapter.execute(params="invalid")  # type: ignore[arg-type]
