from __future__ import annotations

from packages.integrations.training_sim.ghosts import GhostsAdapter


def test_manifest_metadata_is_loaded() -> None:
    manifest = GhostsAdapter(mode="airgapped").get_manifest()
    assert manifest.slug == "ghosts"
    assert manifest.domain == "training_sim"
    assert manifest.license == "Unknown"


def test_validate_availability_true_in_airgapped_mode() -> None:
    assert GhostsAdapter(mode="airgapped").validate_availability() is True


def test_execute_returns_fixture_when_airgapped() -> None:
    response = GhostsAdapter(mode="airgapped").execute({"operation": "range_exercise_run"})
    assert response["source"] == "fixture"
    assert response["result"]["range_id"] == "cyber-range-joint-17"
