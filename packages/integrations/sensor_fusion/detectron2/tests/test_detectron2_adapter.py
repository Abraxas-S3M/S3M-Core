from __future__ import annotations

from packages.integrations.sensor_fusion.detectron2.adapter import Detectron2Adapter


def test_manifest_metadata_is_loaded() -> None:
    manifest = Detectron2Adapter(mode="airgapped").get_manifest()
    assert manifest.slug == "detectron2"
    assert manifest.domain == "sensor_fusion"
    assert manifest.license == "Apache 2.0"


def test_validate_availability_true_in_airgapped_mode() -> None:
    assert Detectron2Adapter(mode="airgapped").validate_availability() is True


def test_execute_returns_fixture_when_airgapped() -> None:
    response = Detectron2Adapter(mode="airgapped").execute({"operation": "instance_segmentation_readiness"})
    assert response["source"] == "fixture"
    assert response["result"]["snapshot_id"] == "detectron2-s3m-2026-04-10T122000Z"
