from __future__ import annotations

import importlib.util
from pathlib import Path


def _load_adapter():
    adapter_path = Path(__file__).resolve().parents[1] / "adapter.py"
    spec = importlib.util.spec_from_file_location(
        "s3m_nato_awesome_threat_intelligence_adapter_under_test",
        adapter_path,
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.AwesomeThreatIntelligencecuratedAdapter


def test_manifest_metadata_is_loaded():
    adapter_cls = _load_adapter()
    manifest = adapter_cls(mode="airgapped").get_manifest()
    assert manifest.slug == "awesome-threat-intelligence-curated-list"
    assert manifest.domain == "nato"
    assert manifest.license == "MIT"


def test_validate_availability_true_in_airgapped_mode():
    adapter_cls = _load_adapter()
    assert adapter_cls(mode="airgapped").validate_availability() is True


def test_execute_returns_fixture_when_airgapped():
    adapter_cls = _load_adapter()
    response = adapter_cls(mode="airgapped").execute({"operation": "recommend_sources"})
    assert response["source"] == "fixture"
    assert response["result"]["curation_id"] == "ati-2026-04-09-1880"
