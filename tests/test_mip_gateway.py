"""Unit tests for tactical MIP gateway and mapper workflows."""

from __future__ import annotations

from services.interop.mip import MIPDataModel, MIPGateway, MIPObjectMapper
from services.interop.msdl import ORBATManager


def _mip_test_config(tmp_path) -> dict:
    return {
        "baseline": "4.3",
        "data_model": "MIM",
        "gateway_url": None,
        "oig_categories": ["operations", "intelligence", "logistics", "plans", "cop"],
        "publish_interval_seconds": 10,
        "outbox_dir": str(tmp_path / "mip_outbox"),
        "inbox_dir": str(tmp_path / "mip_inbox"),
    }


def test_create_object_item_unit():
    model = MIPDataModel()
    obj = model.create_object_item(
        name="Enemy Infantry Platoon",
        category="unit",
        hostility="hostile",
        sidc="10061000151211000000",
    )
    assert obj.object_item_id
    assert obj.name == "Enemy Infantry Platoon"
    assert obj.category == "unit"
    assert obj.hostility_status == "hostile"
    assert obj.operational_status == "operational"


def test_create_location_riyadh():
    model = MIPDataModel()
    location = model.create_location(
        object_item_id="obj-riyadh",
        lat=24.7136,
        lon=46.6753,
        alt=612.0,
        bearing=35.0,
        speed=5.5,
    )
    assert location.object_item_id == "obj-riyadh"
    assert location.latitude == 24.7136
    assert location.longitude == 46.6753
    assert location.altitude == 612.0
    assert location.bearing == 35.0
    assert location.speed == 5.5


def test_s3m_track_to_mip_roundtrip():
    mapper = MIPObjectMapper()
    original_track = {
        "unit_id": "falcon-uav-1",
        "entity_type": "FRIENDLY_UAV",
        "affiliation": "friendly",
        "position": [24.7136, 46.6753, 620.0],
        "heading": 90.0,
        "speed": 41.0,
        "sidc": "10031000141211000000",
        "status": "active",
    }
    obj, loc = mapper.s3m_track_to_mip(original_track)
    recovered_track = mapper.mip_to_s3m_track(obj, loc)
    assert recovered_track["entity_type"] == "FRIENDLY_UAV"
    assert recovered_track["position"][0] == original_track["position"][0]
    assert recovered_track["position"][1] == original_track["position"][1]
    assert recovered_track["position"][2] == original_track["position"][2]


def test_s3m_mission_to_mip_task():
    mapper = MIPObjectMapper()
    mission = {
        "mission_id": "mission-1",
        "mission_type": "PATROL",
        "unit_id": "unit-alpha",
        "start_time": "2026-04-15T10:00:00+00:00",
        "end_time": "2026-04-15T12:00:00+00:00",
        "objective_location": {"lat": 24.7, "lon": 46.6, "alt": 600.0},
        "description": "Patrol route Alpha.",
    }
    task = mapper.s3m_mission_to_mip_task(mission)
    assert task.action_type == "patrol"
    assert task.responsible_unit == "unit-alpha"
    assert task.objective_location is not None
    assert task.objective_location.latitude == 24.7


def test_orbat_to_oig_saudi_template():
    manager = ORBATManager()
    force = manager.create_saudi_template()
    mapper = MIPObjectMapper()
    oig = mapper.s3m_orbat_to_mip_oig(force)
    assert oig.category == "operations"
    assert len(oig.items) == len(force.units)
    for unit in force.units:
        assert unit.unit_id in oig.items


def test_mip_xml_serialize_parse_roundtrip():
    model = MIPDataModel()
    obj = model.create_object_item(
        name="Royal Guard HQ",
        category="unit",
        hostility="friend",
        sidc="10031000141211000000",
    )
    xml = model.to_xml([obj])
    parsed = model.from_xml(xml)
    assert len(parsed) == 1
    parsed_obj = parsed[0]
    assert parsed_obj.object_item_id == obj.object_item_id
    assert parsed_obj.name == obj.name
    assert parsed_obj.category == obj.category


def test_cop_oig_contains_all_friendly_tracks(tmp_path):
    gateway = MIPGateway(config=_mip_test_config(tmp_path))
    tracks = [
        {
            "unit_id": "blue-uav-1",
            "entity_type": "FRIENDLY_UAV",
            "affiliation": "friendly",
            "position": [24.71, 46.67, 610.0],
        },
        {
            "unit_id": "blue-ugv-2",
            "entity_type": "FRIENDLY_UGV",
            "affiliation": "friendly",
            "position": [24.72, 46.68, 605.0],
        },
        {
            "unit_id": "red-inf-9",
            "entity_type": "ENEMY_INFANTRY",
            "affiliation": "hostile",
            "position": [24.73, 46.69, 590.0],
        },
    ]
    published = gateway.exchange_cop(tracks)
    assert published == 2
    assert gateway.published_oigs
    cop_oig = gateway.published_oigs[-1]
    assert cop_oig.category == "cop"
    friendly_ids = {
        object_id
        for object_id, obj in gateway.data_model.object_items.items()
        if obj.hostility_status == "friend"
    }
    assert len(friendly_ids) == 2
    for object_id in friendly_ids:
        assert object_id in cop_oig.items


def test_offline_writes_outbox(tmp_path):
    gateway = MIPGateway(config=_mip_test_config(tmp_path))
    oig = gateway.data_model.create_oig(category="operations", unit_id="hq-1")
    ok = gateway.publish_oig(oig)
    assert ok is True
    queued = list((tmp_path / "mip_outbox").glob("*.xml"))
    assert len(queued) == 1
    payload = queued[0].read_text(encoding="utf-8")
    assert "<MIPExchange" in payload
