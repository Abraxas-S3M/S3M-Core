"""Tests for C2SIMMessageFactory."""

from services.interop.c2sim.message_factory import C2SIMMessageFactory


def test_create_order_generates_valid_xml():
    factory = C2SIMMessageFactory()
    xml = factory.create_order(
        order_id="ord-1",
        issuer="HQ",
        task_type="Advance",
        assigned_units=["unit-1", "unit-2"],
        waypoints=[(24.7, 46.6, 0.0)],
        roe="SELF_DEFENSE_ONLY",
    )
    assert "<Order" in xml
    assert "<OrderID>ord-1</OrderID>" in xml
    assert "TaskingOrder" in xml


def test_parse_order_roundtrip():
    factory = C2SIMMessageFactory()
    xml = factory.create_order(
        order_id="ord-2",
        issuer="HQ",
        task_type="Patrol",
        assigned_units=["u1"],
        waypoints=[(24.0, 46.0, 10.0)],
        roe="ROE-A",
    )
    parsed = factory.parse_order(xml)
    assert parsed["order_id"] == "ord-2"
    assert parsed["assigned_units"] == ["u1"]
    assert parsed["task_type"] == "Patrol"


def test_create_report_generates_valid_xml():
    factory = C2SIMMessageFactory()
    xml = factory.create_report("rep-1", "u1", "PositionReport", {"lat": 24.7, "lon": 46.6})
    assert "<Report" in xml
    assert "<ReportType>PositionReport</ReportType>" in xml


def test_create_initialization_includes_forces_and_environment():
    factory = C2SIMMessageFactory()
    xml = factory.create_initialization(
        {
            "scenario_id": "scn-1",
            "name": "Init",
            "forces": [{"force_id": "f1", "force_name": "Blue", "units": []}],
            "environment": {"terrain": "desert"},
        }
    )
    assert "<Initialization" in xml
    assert "<Forces>" in xml
    assert "<Environment>" in xml


def test_parse_any_autodetect_order_vs_report():
    factory = C2SIMMessageFactory()
    order_xml = factory.create_order("o1", "HQ", "Move", ["u1"], [(1, 2, 0)], "ROE")
    report_xml = factory.create_report("r1", "u1", "StatusReport", {"state": "ok"})
    assert factory.parse_any(order_xml)["message_type"] == "Order"
    assert factory.parse_any(report_xml)["message_type"] == "Report"


def test_validate_catches_malformed_xml():
    factory = C2SIMMessageFactory()
    ok, errors = factory.validate("<Order><Bad></Order")
    assert ok is False
    assert errors
