"""Unit tests for the S3M HLA federate adapter and DIS bridge."""

from __future__ import annotations

from pathlib import Path
import xml.etree.ElementTree as ET

import pytest

from services.interop.hla.dis_hla_bridge import DISHLABridge
from services.interop.hla.federate_adapter import HLAFederateAdapter
from services.interop.models import DISEntityType


def _build_stub_adapter() -> HLAFederateAdapter:
    return HLAFederateAdapter(
        {
            "rti_type": "stub",
            "federation_name": "S3M_Test_Fed",
            "fom_path": "configs/interop/s3m_fom.xml",
            "time_step_seconds": 0.1,
        }
    )


def test_stub_mode_create_join_federation():
    adapter = _build_stub_adapter()
    assert adapter.create_federation("S3M_Test_Fed", "configs/interop/s3m_fom.xml") is True
    assert adapter.join_federation("S3M_Test_Fed") is True
    status = adapter.get_federation_status()
    assert status["mode"] == "stub"
    assert status["joined"] is True
    assert adapter.resign_federation() is True
    assert adapter.destroy_federation("S3M_Test_Fed") is True


def test_stub_publish_and_reflect_object():
    adapter = _build_stub_adapter()
    assert adapter.create_federation("S3M_Test_Fed", "configs/interop/s3m_fom.xml")
    assert adapter.join_federation("S3M_Test_Fed")
    assert adapter.publish_object_class("Aircraft", ["Position", "Velocity", "Marking"])
    assert adapter.subscribe_object_class("Aircraft", ["Position", "Velocity", "Marking"])

    reflections = []
    adapter.reflect_object(lambda payload: reflections.append(payload))

    updated = adapter.update_object(
        class_name="Aircraft",
        object_handle=12,
        attributes={
            "Position": {"lat": 24.7136, "lon": 46.6753, "alt": 620.0},
            "Velocity": {"x": 10.0, "y": 2.0, "z": 0.0},
            "Marking": "UAV-12",
        },
    )
    assert updated is True
    assert len(reflections) == 1
    assert reflections[0]["class_name"] == "Aircraft"
    assert reflections[0]["attributes"]["Position"].startswith("24.713600,46.675300")


def test_stub_send_receive_interaction():
    adapter = _build_stub_adapter()
    assert adapter.create_federation("S3M_Test_Fed", "configs/interop/s3m_fom.xml")
    assert adapter.join_federation("S3M_Test_Fed")

    interactions = []
    adapter.receive_interaction(lambda payload: interactions.append(payload))
    sent = adapter.send_interaction(
        "WeaponFire",
        {"FiringObjectIdentifier": "UAV-12", "TargetObjectIdentifier": "RED-2", "MunitionType": "AIM-9"},
    )
    assert sent is True
    assert len(interactions) == 1
    assert interactions[0]["class_name"] == "WeaponFire"


def test_dis_to_hla_bridge_aircraft():
    adapter = _build_stub_adapter()
    assert adapter.create_federation("S3M_Test_Fed", "configs/interop/s3m_fom.xml")
    assert adapter.join_federation("S3M_Test_Fed")
    assert adapter.subscribe_object_class("Aircraft", ["Position", "Velocity", "Marking"])
    bridge = DISHLABridge(adapter)

    bridge.sync_from_dis(
        {
            "entity_id": 501,
            "entity_type": DISEntityType(kind=1, domain=2, country=178, category=1, subcategory=0, specific=0, extra=0),
            "position": {"lat": 24.80, "lon": 46.70, "alt": 1500.0},
            "velocity": {"x": 80.0, "y": 0.0, "z": -1.0},
            "marking": "BLUE-UAV-501",
            "force_id": 1,
        }
    )

    objects = adapter.get_objects()
    assert len(objects) == 1
    assert objects[0]["class_name"] == "Aircraft"
    assert objects[0]["attributes"]["Marking"] == "BLUE-UAV-501"


def test_hla_to_s3m_track_conversion():
    bridge = DISHLABridge(_build_stub_adapter())
    track = bridge.sync_from_hla(
        {
            "class_name": "GroundVehicle",
            "object_handle": 77,
            "attributes": {
                "Position": "24.123456,46.654321,125.0",
                "DamageState": "active",
            },
        }
    )
    assert track["unit_id"] == "hla-GroundVehicle-77"
    assert track["role"] == "groundvehicle"
    assert track["status"] == "active"
    assert track["position"] == [24.123456, 46.654321, 125.0]


def test_time_advancement_stub():
    adapter = _build_stub_adapter()
    assert adapter.create_federation("S3M_Test_Fed", "configs/interop/s3m_fom.xml")
    assert adapter.join_federation("S3M_Test_Fed")
    for _ in range(10):
        assert adapter.advance_time(0.1)
    health = adapter.health_check()
    assert health["backend"]["logical_time"] == pytest.approx(1.0)


def test_fom_path_reads_s3m_fom():
    fom_path = Path("configs/interop/s3m_fom.xml")
    assert fom_path.exists()
    root = ET.fromstring(fom_path.read_text(encoding="utf-8"))
    assert root.tag == "fom"
    object_classes = root.findall(".//objectClass")
    assert any(node.attrib.get("name") == "Aircraft" for node in object_classes)
