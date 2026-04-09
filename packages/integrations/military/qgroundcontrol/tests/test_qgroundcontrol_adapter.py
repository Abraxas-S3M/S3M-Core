from __future__ import annotations

from packages.integrations.military.qgroundcontrol.adapter import QgroundcontrolAdapter


def test_manifest_metadata_is_loaded() -> None:
    manifest = QgroundcontrolAdapter(mode="airgapped").get_manifest()
    assert manifest.slug == "qgroundcontrol"
    assert manifest.domain == "military"
    assert manifest.license == "Apache 2.0"


def test_validate_availability_true_in_airgapped_mode() -> None:
    assert QgroundcontrolAdapter(mode="airgapped").validate_availability() is True


def test_execute_returns_fixture_when_airgapped() -> None:
    response = QgroundcontrolAdapter(mode="airgapped").execute({"operation": "plan_mission"})
    assert response["source"] == "fixture"
    assert response["result"]["mission_plan_id"] == "qgc-sortie-2026-04-09-004"
