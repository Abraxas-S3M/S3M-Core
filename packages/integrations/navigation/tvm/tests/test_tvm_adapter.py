from __future__ import annotations

from packages.integrations.navigation.tvm.adapter import TvmAdapter


def test_manifest_metadata_is_loaded():
    manifest = TvmAdapter(mode="airgapped").get_manifest()
    assert manifest.slug == "tvm"
    assert manifest.domain == "navigation"
    assert manifest.license == "Apache 2.0"


def test_validate_availability_true_in_airgapped_mode():
    assert TvmAdapter(mode="airgapped").validate_availability() is True


def test_execute_returns_fixture_when_airgapped():
    response = TvmAdapter(mode="airgapped").execute({"operation": "compile_model"})
    assert response["source"] == "fixture"
    assert response["result"]["event_id"] == "tvm-nav-2026-04-09-014"
