from __future__ import annotations

from packages.integrations.military.crazyswarm.adapter import CrazyswarmAdapter


def test_manifest_metadata_is_loaded() -> None:
    manifest = CrazyswarmAdapter(mode="airgapped").get_manifest()
    assert manifest.slug == "crazyswarm"
    assert manifest.domain == "military"
    assert manifest.license == "MIT"


def test_validate_availability_true_in_airgapped_mode() -> None:
    assert CrazyswarmAdapter(mode="airgapped").validate_availability() is True


def test_execute_returns_fixture_when_airgapped() -> None:
    response = CrazyswarmAdapter(mode="airgapped").execute({"operation": "coordinate_swarm"})
    assert response["source"] == "fixture"
    assert response["result"]["mission_id"] == "crazyswarm-stack-2026-04-09-007"
