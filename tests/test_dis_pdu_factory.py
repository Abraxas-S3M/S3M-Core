"""Unit tests for Phase 16 DIS PDU factory."""

from __future__ import annotations

from services.interop.dis import DISPDUFactory
from services.interop.models import (
    DISEntityID,
    DISEntityType,
    DISLinearVelocity,
    DISOrientation,
    DISPDUType,
    DISWorldCoordinate,
)


def _sample_entity():
    return {
        "entity_id": DISEntityID(1, 1, 42),
        "entity_type": DISEntityType(1, 1, 178, 1, 0, 0, 0),
        "position": DISWorldCoordinate.from_lat_lon_alt(24.7136, 46.6753, 0.0),
        "orientation": DISOrientation(0.1, 0.2, 0.3),
        "velocity": DISLinearVelocity(5.0, 0.0, 0.0),
    }


def test_encode_entity_state_length_144_bytes():
    fac = DISPDUFactory()
    s = _sample_entity()
    pdu = fac.encode_entity_state(
        s["entity_id"],
        s["entity_type"],
        s["position"],
        s["orientation"],
        s["velocity"],
        force_id=1,
        exercise_id=7,
        marking="SAUDI-ALPHA",
    )
    assert isinstance(pdu, bytes)
    assert len(pdu) == 144


def test_decode_entity_state_roundtrip():
    fac = DISPDUFactory()
    s = _sample_entity()
    pdu = fac.encode_entity_state(
        s["entity_id"], s["entity_type"], s["position"], s["orientation"], s["velocity"], 1, 7, "ALPHA-UNIT1"
    )
    decoded = fac.decode_entity_state(pdu)
    assert decoded["entity_id"] == s["entity_id"]
    assert decoded["entity_type"].country == 178
    assert decoded["marking"] == "ALPHA-UNIT1"


def test_entity_position_preserved_roundtrip():
    fac = DISPDUFactory()
    s = _sample_entity()
    pdu = fac.encode_entity_state(
        s["entity_id"], s["entity_type"], s["position"], s["orientation"], s["velocity"], 1, 7
    )
    decoded = fac.decode_entity_state(pdu)
    assert abs(decoded["position"].x - s["position"].x) < 1e-6
    assert abs(decoded["position"].y - s["position"].y) < 1e-6
    assert abs(decoded["position"].z - s["position"].z) < 1e-6


def test_force_id_mapping_friendly_hostile_neutral():
    fac = DISPDUFactory()
    s = _sample_entity()
    pdu_f = fac.encode_entity_state(
        s["entity_id"], s["entity_type"], s["position"], s["orientation"], s["velocity"], 1, 1
    )
    pdu_h = fac.encode_entity_state(
        s["entity_id"], s["entity_type"], s["position"], s["orientation"], s["velocity"], 2, 1
    )
    pdu_n = fac.encode_entity_state(
        s["entity_id"], s["entity_type"], s["position"], s["orientation"], s["velocity"], 3, 1
    )
    assert fac.decode_entity_state(pdu_f)["force_id"] == 1
    assert fac.decode_entity_state(pdu_h)["force_id"] == 2
    assert fac.decode_entity_state(pdu_n)["force_id"] == 3


def test_entity_marking_11_chars_preserved():
    fac = DISPDUFactory()
    s = _sample_entity()
    marking = "MARKING1234"  # 11 chars
    pdu = fac.encode_entity_state(
        s["entity_id"], s["entity_type"], s["position"], s["orientation"], s["velocity"], 1, 1, marking=marking
    )
    assert fac.decode_entity_state(pdu)["marking"] == marking


def test_fire_roundtrip():
    fac = DISPDUFactory()
    firing = DISEntityID(1, 1, 10)
    target = DISEntityID(1, 1, 20)
    mun = DISEntityType(2, 1, 178, 1, 0, 0, 0)
    loc = DISWorldCoordinate.from_lat_lon_alt(24.0, 46.0, 0.0)
    pdu = fac.encode_fire(firing, target, mun, loc, exercise_id=1)
    decoded = fac.decode_fire(pdu)
    assert decoded["firing_entity"] == firing
    assert decoded["target_entity"] == target


def test_detonation_roundtrip():
    fac = DISPDUFactory()
    firing = DISEntityID(1, 1, 10)
    target = DISEntityID(1, 1, 20)
    mun = DISEntityType(2, 1, 178, 1, 0, 0, 0)
    loc = DISWorldCoordinate.from_lat_lon_alt(24.0, 46.0, 0.0)
    pdu = fac.encode_detonation(firing, target, loc, mun, result=1, exercise_id=1)
    decoded = fac.decode_detonation(pdu)
    assert decoded["firing_entity"] == firing
    assert decoded["target_entity"] == target
    assert decoded["result"] == 1


def test_identify_pdu_type_entity_fire_detonation():
    fac = DISPDUFactory()
    s = _sample_entity()
    entity = fac.encode_entity_state(
        s["entity_id"], s["entity_type"], s["position"], s["orientation"], s["velocity"], 1, 1
    )
    fire = fac.encode_fire(DISEntityID(1, 1, 1), DISEntityID(1, 1, 2), s["entity_type"], s["position"], 1)
    det = fac.encode_detonation(
        DISEntityID(1, 1, 1), DISEntityID(1, 1, 2), s["position"], s["entity_type"], result=2, exercise_id=1
    )
    assert fac.identify_pdu_type(entity) == DISPDUType.ENTITY_STATE
    assert fac.identify_pdu_type(fire) == DISPDUType.FIRE
    assert fac.identify_pdu_type(det) == DISPDUType.DETONATION
