from __future__ import annotations

from packages.integrations.swarm.remroc.adapter import RemrocAdapter


def test_manifest_metadata_is_loaded() -> None:
    manifest = RemrocAdapter(mode="airgapped").get_manifest()
    assert manifest.slug == "remroc"
    assert manifest.domain == "swarm"
    assert manifest.license == "MIT"


def test_validate_availability_true_in_airgapped_mode() -> None:
    assert RemrocAdapter(mode="airgapped").validate_availability() is True


def test_execute_returns_fixture_when_airgapped() -> None:
    response = RemrocAdapter(mode="airgapped").execute(
        {"operation": "simulate_multi_robot_coordination"}
    )
    assert response["source"] == "fixture"
    assert response["result"]["scenario_id"] == "remroc-urban-corridor-2026-04-10-001"

