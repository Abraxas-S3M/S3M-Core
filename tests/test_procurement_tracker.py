from __future__ import annotations

from services.maintenance.models import (
    MaintenanceType,
    ProcurementStatus,
    WorkOrder,
    WorkOrderPriority,
    WorkOrderStatus,
)
from services.maintenance.procurement.procurement_tracker import ProcurementTracker
from services.maintenance.procurement.spare_parts import SparePartsManager
from datetime import datetime, timezone


def _work_order_missing_parts() -> WorkOrder:
    return WorkOrder(
        work_order_id="wo-test-1",
        asset_id="asset-1",
        title="Test WO",
        description="desc",
        maintenance_type=MaintenanceType.PREDICTIVE,
        priority=WorkOrderPriority.URGENT,
        status=WorkOrderStatus.DRAFT,
        assigned_technician=None,
        estimated_hours=6.0,
        parts_required=[
            {"part_id": "P-1", "name": "Rotor", "quantity": 2, "in_stock": False},
            {"part_id": "P-2", "name": "Seal", "quantity": 1, "in_stock": True},
        ],
        created_at=datetime.now(timezone.utc),
    )


def test_create_request_and_get_request():
    tracker = ProcurementTracker()
    req = tracker.create_request("Rotor", "P-1", 2, WorkOrderPriority.URGENT)
    got = tracker.get_request(req.request_id)
    assert got is not None
    assert got.part_name == "Rotor"


def test_approve_changes_status():
    tracker = ProcurementTracker()
    req = tracker.create_request("Rotor", "P-1", 2, WorkOrderPriority.URGENT)
    tracker.approve(req.request_id, approved_by="officer-1")
    updated = tracker.get_request(req.request_id)
    assert updated is not None
    assert updated.status == ProcurementStatus.APPROVED


def test_auto_generate_from_work_orders_creates_requests_for_missing_parts():
    tracker = ProcurementTracker()
    wo = _work_order_missing_parts()
    rows = tracker.auto_generate_from_work_orders([wo])
    assert len(rows) == 1
    assert rows[0].part_number == "P-1"


def test_auto_generate_from_inventory_creates_restock_requests():
    tracker = ProcurementTracker()
    sp = SparePartsManager()
    p1 = sp.add_part("Seal Kit", "SK-1", 4, 5, 20, 15.0, "A", ["TANK"])
    p2 = sp.add_part("Filter", "F-1", 10, 5, 15, 4.0, "B", ["TANK"])
    rows = tracker.auto_generate_from_inventory([p1, p2])
    assert len(rows) == 1
    assert rows[0].part_number == "SK-1"
