from __future__ import annotations

from services.maintenance.procurement import SparePartsManager


def test_add_part_and_get_part():
    mgr = SparePartsManager()
    part = mgr.add_part("Oil Filter", "OF-1", 10, 5, 20, 25.0, "D1", ["TANK"])
    fetched = mgr.get_part(part.part_id)
    assert fetched is not None
    assert fetched.part_number == "OF-1"


def test_consume_decrements_quantity():
    mgr = SparePartsManager()
    part = mgr.add_part("Seal", "SL-1", 10, 2, 10, 10.0, "D1", ["FIGHTER_JET"])
    assert mgr.consume(part.part_id, 3)
    assert mgr.get_part(part.part_id).quantity_on_hand == 7


def test_restock_increments_quantity():
    mgr = SparePartsManager()
    part = mgr.add_part("Bearing", "BR-1", 1, 2, 5, 15.0, "D2", ["HELICOPTER"])
    mgr.restock(part.part_id, 4)
    assert mgr.get_part(part.part_id).quantity_on_hand == 5


def test_check_reorder_returns_parts_below_threshold():
    mgr = SparePartsManager()
    p1 = mgr.add_part("A", "A-1", 1, 2, 5, 1.0, "L1", ["TANK"])
    mgr.add_part("B", "B-1", 10, 2, 5, 1.0, "L1", ["TANK"])
    reorder = mgr.check_reorder()
    assert any(p.part_id == p1.part_id for p in reorder)


def test_create_standard_inventory_creates_20_parts():
    mgr = SparePartsManager()
    rows = mgr.create_standard_inventory()
    assert len(rows) == 20
