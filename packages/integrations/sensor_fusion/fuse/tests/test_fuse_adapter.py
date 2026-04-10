from __future__ import annotations

from packages.integrations.sensor_fusion.fuse.adapter import FuseAdapter


def test_manifest_metadata_is_loaded() -> None:
    manifest = FuseAdapter(mode="airgapped").get_manifest()
    assert manifest.slug == "fuse"
    assert manifest.domain == "sensor_fusion"
    assert manifest.license == "BSD"


def test_validate_availability_true_in_airgapped_mode() -> None:
    assert FuseAdapter(mode="airgapped").validate_availability() is True


def test_execute_returns_fixture_when_airgapped() -> None:
    response = FuseAdapter(mode="airgapped").execute({"operation": "nonlinear_state_estimation_cycle"})
    assert response["source"] == "fixture"
    assert response["result"]["snapshot_id"] == "fuse-s3m-2026-04-10T120000Z"
