from __future__ import annotations

from datetime import datetime, timedelta, timezone

from services.maintenance.assets import AssetRegistry
from services.maintenance.models import AssetCondition, MaintenanceType, WorkOrderPriority, WorkOrderStatus
from services.maintenance.procurement import MaintenanceScheduler, SparePartsManager


def _prepare_asset_registry():
    reg = AssetRegistry()
    a1 = reg.register("F-15SA", "F-15SA #301", "FIGHTER_JET", "SN-F15-301", "S3M", "F-15SA", "Base-A", "Wing-A", 4600)
    a2 = reg.register("M1A2 Abrams", "M1A2 #301", "TANK", "SN-TNK-301", "S3M", "M1A2", "Base-B", "Brigade-B", 5200)
    a1.next_maintenance = datetime.now(timezone.utc) - timedelta(days=1)
    a2.rul_hours = 300.0
    return reg, a1, a2


def test_generate_work_orders_creates_preventive_for_past_due_assets():
    reg, a1, _ = _prepare_asset_registry()
    scheduler = MaintenanceScheduler(asset_registry=reg, spare_parts=SparePartsManager())
    orders = scheduler.generate_work_orders()
    assert any(o.asset_id == a1.asset_id and o.maintenance_type == MaintenanceType.PREVENTIVE for o in orders)


def test_generate_work_orders_creates_predictive_for_low_rul_assets():
    reg, _, a2 = _prepare_asset_registry()
    a2.rul_hours = 150.0
    scheduler = MaintenanceScheduler(asset_registry=reg, spare_parts=SparePartsManager())
    orders = scheduler.generate_work_orders()
    assert any(o.asset_id == a2.asset_id and o.maintenance_type == MaintenanceType.PREDICTIVE for o in orders)
    assert any(o.priority in {WorkOrderPriority.URGENT, WorkOrderPriority.EMERGENCY} for o in orders if o.asset_id == a2.asset_id)


def test_work_order_lifecycle_draft_approved_in_progress_completed():
    reg, *_ = _prepare_asset_registry()
    scheduler = MaintenanceScheduler(asset_registry=reg, spare_parts=SparePartsManager())
    orders = scheduler.generate_work_orders()
    wo = orders[0]
    assert wo.status == WorkOrderStatus.DRAFT

    scheduler.approve_work_order(wo.work_order_id, approved_by="maint-chief")
    assert scheduler.work_orders[wo.work_order_id].status == WorkOrderStatus.APPROVED

    scheduler.start_work_order(wo.work_order_id, technician="tech-17")
    assert scheduler.work_orders[wo.work_order_id].status == WorkOrderStatus.IN_PROGRESS

    scheduler.complete_work_order(wo.work_order_id, notes="complete", parts_used=[], cost=1234.5)
    assert scheduler.work_orders[wo.work_order_id].status == WorkOrderStatus.COMPLETED
    assert scheduler.work_orders[wo.work_order_id].actual_cost == 1234.5


def test_get_schedule_returns_calendar_view():
    reg, *_ = _prepare_asset_registry()
    scheduler = MaintenanceScheduler(asset_registry=reg, spare_parts=SparePartsManager())
    scheduler.generate_work_orders()
    schedule = scheduler.get_schedule(days_ahead=30)
    assert isinstance(schedule, list)
    if schedule:
        assert "date" in schedule[0]
        assert "work_orders" in schedule[0]
        assert "assets_affected" in schedule[0]


def test_get_backlog_returns_approved_but_not_started():
    reg, *_ = _prepare_asset_registry()
    scheduler = MaintenanceScheduler(asset_registry=reg, spare_parts=SparePartsManager())
    orders = scheduler.generate_work_orders()
    target = orders[0]
    scheduler.approve_work_order(target.work_order_id, approved_by="ops")
    backlog = scheduler.get_backlog()
    assert any(o.work_order_id == target.work_order_id for o in backlog)
