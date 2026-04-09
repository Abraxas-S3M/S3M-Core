from __future__ import annotations

from packages.integrations.military.mavros.adapter import MavrosAdapter


def test_manifest_metadata_is_loaded() -> None:
    manifest = MavrosAdapter(mode="airgapped").get_manifest()
    assert manifest.slug == "mavros"
    assert manifest.domain == "military"
    assert manifest.license == "BSD"


def test_validate_availability_true_in_airgapped_mode() -> None:
    assert MavrosAdapter(mode="airgapped").validate_availability() is True


def test_execute_returns_fixture_when_airgapped() -> None:
    response = MavrosAdapter(mode="airgapped").execute({"operation": "bridge_telemetry"})
    assert response["source"] == "fixture"
    assert response["result"]["bridge_session_id"] == "mavros-bridge-2026-04-09-015"
