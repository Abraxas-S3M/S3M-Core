"""Integration test for NATO adapter wiring across S3M interop surfaces.

Military/tactical context:
This validates that CWIX-style coalition data can traverse all NATO standards
paths while remaining offline-capable for austere deployment rehearsals.
"""

from __future__ import annotations

from services.interop.cot import CotBridge, CotEventFactory, CotTransport
from src.security.interop import InteropManager


class _OfflineCotTransport(CotTransport):
    """Deterministic CoT transport for offline CWIX rehearsal validation."""

    def send(self, xml: str) -> bool:
        return bool(str(xml).strip())

    def receive(self) -> str | None:
        return None


def test_nato_interop_wiring_end_to_end(tmp_path) -> None:
    manager = InteropManager()

    # Enable NATO adapters and required bridge endpoints in offline-safe mode.
    assert manager.enable_protocol("cot", {"transport": "offline"}) is True
    cot_transport = _OfflineCotTransport({"cot": {"outbox_dir": str(tmp_path / "cot_outbox")}})
    cot_factory = CotEventFactory({})
    manager._cot_transport = cot_transport
    manager._cot_event_factory = cot_factory
    manager.cot_bridge = CotBridge(transport=cot_transport, event_factory=cot_factory)
    manager._status["cot"]["connected"] = True
    assert manager.enable_protocol("mtf", {"gateway_url": None}) is True
    assert manager.enable_protocol("fmn_security", {"enforce_labels": True, "releasable_to_default": ["SAU", "USA"]}) is True
    assert manager.enable_protocol("hla", {"rti_type": "stub", "federation_name": "S3M_NATO_TEST"}) is True
    assert manager.enable_protocol(
        "mip",
        {
            "outbox_dir": str(tmp_path / "mip_outbox"),
            "inbox_dir": str(tmp_path / "mip_inbox"),
        },
    ) is True
    assert manager.enable_protocol("nvg", {"outbox_dir": str(tmp_path / "nvg_outbox")}) is True
    assert manager.enable_protocol("nsili", {"catalog_dir": str(tmp_path / "nsili_catalog")}) is True
    assert manager.enable_protocol("uas4586", {"max_loi": 3}) is True
    assert manager.enable_protocol("fmv", {"register_in_nsili": True}) is True
    assert manager.enable_protocol("ogc") is True
    assert manager.enable_protocol("link22", {"mode": "stub"}) is True

    # HLA <-> DIS bridge plus MIP/NVG/OGC crossfeed from one entity update.
    send_result = manager.send_entity_update(
        {
            "entity_id": "blue-uav-77",
            "entity_type": "FRIENDLY_UAV",
            "allegiance": "friendly",
            "location": {"lat": 24.7136, "lon": 46.6753, "alt": 620.0},
            "velocity": {"x": 10.0, "y": 0.0, "z": 0.0},
            "marking": "EAGLE-77",
            "status": "active",
        }
    )
    assert send_result["hla"] is True
    assert send_result["mip"] is True
    assert send_result["nvg"] is True
    assert send_result["ogc"] is True

    hla_objects = manager.hla_adapter.get_objects()
    assert len(hla_objects) >= 1
    bridged_track = manager.hla_dis_bridge.sync_from_hla(hla_objects[0])
    assert bridged_track["unit_id"].startswith("hla-")

    # UAS 4586 vehicle status should bridge into CoT track publishing.
    registration = manager.register_uas_platform("falcon-uav-1", "MALE", ["LOI1", "LOI2", "LOI3"])
    assert registration["effective_loi"] == 3
    uas_result = manager.publish_uas_vehicle_status(
        "falcon-uav-1",
        {
            "position": {"lat": 24.7136, "lon": 46.6753, "altitude": 800.0},
            "speed": 45.0,
            "heading": 120.0,
            "fuel": 80.0,
            "mode": "ON_STATION",
        },
    )
    assert uas_result["published"] is True
    assert uas_result["cot"] is True

    # FMV metadata should register into NSILI catalog.
    fmv_result = manager.register_fmv_with_nsili(
        uav_status={"platform_heading": 90.0, "position": {"latitude": 24.7, "longitude": 46.6, "altitude": 900.0}},
        payload_status={"sensor_position": {"latitude": 24.7, "longitude": 46.6, "altitude": 905.0}, "uas_local_set_version": 13},
        timestamp=1_713_264_321.0,
        video_reference="droneops://cwix/fmv-77",
    )
    assert fmv_result["registered"] is True
    assert manager.nsili_catalog.has_product(fmv_result["product_id"]) is True

    # FMN labeling requirement: outbound records carry NATO security label metadata.
    mtf_result = manager.send_mtf_message(
        report_type="INTSUM",
        content={"summary_text": "NATO adapters synchronized.", "assessment_text": "CWIX flow nominal."},
        originator="S3M J2",
        classification="SECRET",
    )
    assert mtf_result["accepted"] is True
    outbound = manager.get_message_history(direction="outbound", limit=30)
    assert any("_fmn_security_label" in str(row.get("data", "")) for row in outbound)

    # Link22 remains stubbed but wired into manager surface.
    assert manager.publish_link22_track({"id": "l22-1", "entity_type": "FRIENDLY_SHIP"}) is False
    assert manager.link22_adapter.health_check()["status"] == "stub"

    # Verifier includes NATO adapter readiness suites in integrated report.
    verification = manager.health_check()
    assert verification["status"] == "operational"
