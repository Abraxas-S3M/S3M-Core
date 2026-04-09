"""Unit tests for dashboard integration adapter wrappers."""

from __future__ import annotations

import importlib

import pytest


CASES: list[dict[str, str]] = [
    {
        "name": "World Monitor",
        "slug": "world-monitor",
        "class_name": "WorldMonitorAdapter",
        "license": "MIT",
        "source_url": "https://github.com/koala73/worldmonitor",
    },
    {
        "name": "MISP-Dashboard",
        "slug": "misp-dashboard",
        "class_name": "MispDashboardAdapter",
        "license": "AGPL-3.0",
        "source_url": "https://github.com/MISP/misp-dashboard",
    },
    {
        "name": "Streamlit-Cybersecurity-Dashboard",
        "slug": "streamlit-cybersecurity-dashboard",
        "class_name": "StreamlitCybersecurityDashboardAdapter",
        "license": "MIT",
        "source_url": "https://github.com/ajitagupta/streamlit-cybersecurity-dashboard",
    },
    {
        "name": "Supply-Chain-Management-Dashboard",
        "slug": "supply-chain-management-dashboard",
        "class_name": "SupplyChainManagementDashboardAdapter",
        "license": "MIT",
        "source_url": "https://github.com/GirishKumarV25/Supply-Chain-Management-Dashboard",
    },
    {
        "name": "Supply-Chain-Performance-Dashboard",
        "slug": "supply-chain-performance-dashboard",
        "class_name": "SupplyChainPerformanceDashboardAdapter",
        "license": "MIT",
        "source_url": "https://github.com/PolinaBurova/Supply-Chain-Performance-Dashboard",
    },
]


def _load_adapter(case: dict[str, str]):
    module = importlib.import_module(f"packages.integrations.dashboard.{case['slug']}.adapter")
    return getattr(module, case["class_name"])


@pytest.mark.parametrize("case", CASES, ids=[case["slug"] for case in CASES])
def test_package_exports_expected_adapter(case: dict[str, str]) -> None:
    package = importlib.import_module(f"packages.integrations.dashboard.{case['slug']}")
    assert hasattr(package, case["class_name"])


@pytest.mark.parametrize("case", CASES, ids=[case["slug"] for case in CASES])
def test_manifest_loads_expected_metadata(case: dict[str, str]) -> None:
    adapter_class = _load_adapter(case)
    adapter = adapter_class(mode="airgapped")
    manifest = adapter.get_manifest()
    assert manifest.name == case["name"]
    assert manifest.slug == case["slug"]
    assert manifest.domain == "dashboard"
    assert manifest.license == case["license"]
    assert manifest.source_url == case["source_url"]
    assert manifest.integration_type == "adapter"


@pytest.mark.parametrize("case", CASES, ids=[case["slug"] for case in CASES])
def test_logger_name_matches_required_namespace(case: dict[str, str]) -> None:
    adapter_class = _load_adapter(case)
    adapter = adapter_class(mode="airgapped")
    assert adapter.logger.name == f"s3m.integrations.dashboard.{case['slug']}"


@pytest.mark.parametrize("case", CASES, ids=[case["slug"] for case in CASES])
def test_validate_availability_is_true_with_airgapped_fixture(case: dict[str, str]) -> None:
    adapter_class = _load_adapter(case)
    adapter = adapter_class(mode="airgapped")
    assert adapter.validate_availability() is True


@pytest.mark.parametrize("case", CASES, ids=[case["slug"] for case in CASES])
def test_execute_returns_fixture_data_in_airgapped_mode(case: dict[str, str]) -> None:
    adapter_class = _load_adapter(case)
    adapter = adapter_class(mode="airgapped")
    payload = adapter.execute({"operation": "status"})
    assert payload["integration_id"] == case["slug"]
    assert payload["domain"] == "dashboard"
    assert payload["mode"] == "airgapped"
    assert payload["source"] == "fixture"
    assert payload["operation"] == "status"
    assert isinstance(payload["data"], dict)
    assert payload["data"]
