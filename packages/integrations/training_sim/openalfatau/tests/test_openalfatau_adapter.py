from __future__ import annotations

from packages.integrations.training_sim.openalfatau.adapter import OpenalfatauAdapter


def test_manifest_metadata_is_loaded() -> None:
    manifest = OpenalfatauAdapter(mode="airgapped").get_manifest()
    assert manifest.slug == "openalfatau"
    assert manifest.domain == "training_sim"
    assert manifest.license == "Unknown"


def test_validate_availability_true_in_airgapped_mode() -> None:
    assert OpenalfatauAdapter(mode="airgapped").validate_availability() is True


def test_execute_returns_fixture_when_airgapped() -> None:
    response = OpenalfatauAdapter(mode="airgapped").execute({"operation": "library_workflow"})
    assert response["source"] == "fixture"
    assert response["result"]["exercise_id"] == "oat-sim-2026-04-10-echo"
