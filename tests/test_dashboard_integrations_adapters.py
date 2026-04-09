"""Unit tests for dashboard integration wrappers."""

from __future__ import annotations

import importlib.util
from pathlib import Path
from typing import Type

import pytest

from packages.integrations.base import IntegrationAdapter
from packages.integrations.dashboard.assume.adapter import AssumeAdapter
from packages.integrations.dashboard.datascienceinteractivepython.adapter import (
    DatascienceinteractivepythonAdapter,
)
from packages.integrations.dashboard.riskanalysiswithgenerativeaireasoning.adapter import (
    RiskanalysiswithgenerativeaireasoningAdapter,
)
from packages.integrations.registry import discover_integration_manifests


def _load_taiwan_adapter() -> Type[IntegrationAdapter]:
    adapter_path = (
        Path(__file__).resolve().parents[1]
        / "packages"
        / "integrations"
        / "dashboard"
        / "taiwan-situation"
        / "adapter.py"
    )
    module_name = "packages.integrations.dashboard.taiwan_situation.adapter"
    spec = importlib.util.spec_from_file_location(module_name, adapter_path)
    if spec is None or spec.loader is None:
        raise RuntimeError("Unable to load TaiwanSituationAdapter module.")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.TaiwanSituationAdapter


TaiwanSituationAdapter = _load_taiwan_adapter()


@pytest.mark.parametrize(
    ("adapter_cls", "integration_id", "name", "source_url"),
    [
        (
            AssumeAdapter,
            "assume",
            "Assume",
            "https://github.com/assume-framework/assume",
        ),
        (
            DatascienceinteractivepythonAdapter,
            "datascienceinteractivepython",
            "DataScienceInteractivePython",
            "https://github.com/GeostatsGuy/DataScienceInteractivePython",
        ),
        (
            RiskanalysiswithgenerativeaireasoningAdapter,
            "riskanalysiswithgenerativeaireasoning",
            "RiskAnalysisWithGenerativeAIReasoning",
            "https://github.com/bartczernicki/RiskAnalysisWithGenerativeAIReasoning",
        ),
        (
            TaiwanSituationAdapter,
            "taiwan-situation",
            "TaiWan-Situation",
            "https://github.com/Pluto114/TaiWan-situation",
        ),
    ],
)
def test_dashboard_adapter_manifest_and_airgapped_execution(
    adapter_cls: Type[IntegrationAdapter],
    integration_id: str,
    name: str,
    source_url: str,
) -> None:
    adapter = adapter_cls(mode="airgapped")

    manifest = adapter.get_manifest()
    assert manifest.name == name
    assert manifest.slug == integration_id
    assert manifest.domain == "dashboard"
    assert manifest.source_url == source_url
    assert manifest.license == "MIT"
    assert manifest.integration_type == "adapter"
    assert manifest.airgapped_support is True

    assert adapter.logger.name == f"s3m.integrations.dashboard.{integration_id}"
    assert adapter.validate_availability() is True

    response = adapter.execute({"operation": "unit-test"})
    assert response["integration_id"] == integration_id
    assert response["domain"] == "dashboard"
    assert response["mode"] == "airgapped"
    assert response["source"] == "fixture"
    assert response["status"] == "ok"
    assert response["operation"] == "unit-test"
    assert isinstance(response["data"], dict)
    assert response["data"]


def test_dashboard_manifests_discoverable_from_registry() -> None:
    manifests = discover_integration_manifests(Path(__file__).resolve().parents[1] / "packages" / "integrations")
    slugs = {manifest.slug for manifest in manifests if manifest.domain == "dashboard"}
    assert {
        "assume",
        "datascienceinteractivepython",
        "riskanalysiswithgenerativeaireasoning",
        "taiwan-situation",
    }.issubset(slugs)

