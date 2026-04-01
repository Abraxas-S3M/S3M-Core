from __future__ import annotations

from datetime import datetime, timedelta, timezone

from services.maintenance import (
    AssetCondition,
    AssetType,
    AssetRegistry,
    MaintenanceRecord,
    MaintenanceType,
    WorkOrderPriority,
)
from services.maintenance.models import WorkOrderStatus


def _registry() -> AssetRegistry:
    return AssetRegistry()


def _asset(registry: AssetRegistry):
    return registry.register(
        name="F-15SA",
        designation="F-15SA #T1",
        asset_type=AssetType.FIGHTER_JET,
        serial_number="SN-001",
        manufacturer="S3M",
        model="F-15SA",
        location="Base A",
        assigned_unit="Wing A",
        operating_hours=1200,
    )


def test_register_and_get_asset():
    registry = _registry()
    asset = _asset(registry)
    fetched = registry.get_asset(asset.asset_id)
    assert fetched is not None
    assert fetched.designation == "F-15SA #T1"


def test_get_by_designation():
    registry = _registry()
    asset = _asset(registry)
    fetched = registry.get_by_designation("F-15SA #T1")
    assert fetched is not None
    assert fetched.asset_id == asset.asset_id


def test_get_assets_filters():
    registry = _registry()
    a1 = _asset(registry)
    a2 = registry.register(
        name="Truck",
        designation="TRK #1",
        asset_type=AssetType.TRUCK,
        serial_number="SN-TRK-1",
        manufacturer="S3M",
        model="TRK",
        location="Base B",
        assigned_unit="Logistics",
        operating_hours=800,
    )
    registry.update_asset(a2.asset_id, status="DEGRADED")
    jets = registry.get_assets(asset_type=AssetType.FIGHTER_JET)
    degraded = registry.get_assets(status="DEGRADED")
    assert any(a.asset_id == a1.asset_id for a in jets)
    assert any(a.asset_id == a2.asset_id for a in degraded)


def test_update_rul_updates_asset():
    registry = _registry()
    asset = _asset(registry)
    registry.update_rul(asset.asset_id, 88.0, 0.77)
    updated = registry.get_asset(asset.asset_id)
    assert updated.rul_hours == 88.0
    assert updated.rul_confidence == 0.77


def test_record_maintenance_appends_history():
    registry = _registry()
    asset = _asset(registry)
    record = MaintenanceRecord(
        record_id="mr-1",
        asset_id=asset.asset_id,
        work_order_id="wo-1",
        maintenance_type=MaintenanceType.PREVENTIVE,
        description="Inspection",
        performed_by="tech-1",
        performed_at=datetime.now(timezone.utc),
        hours_at_maintenance=asset.operating_hours,
        parts_replaced=[],
        cost=500.0,
        next_recommended=datetime.now(timezone.utc) + timedelta(days=30),
        condition_before=AssetCondition.FAIR,
        condition_after=AssetCondition.GOOD,
    )
    registry.record_maintenance(asset.asset_id, record)
    hist = registry.get_maintenance_history(asset.asset_id)
    assert len(hist) == 1
    assert hist[0].record_id == "mr-1"


def test_get_due_for_maintenance():
    registry = _registry()
    asset = _asset(registry)
    registry.update_asset(asset.asset_id, next_maintenance=datetime.now(timezone.utc) - timedelta(days=1))
    due = registry.get_due_for_maintenance()
    assert any(a.asset_id == asset.asset_id for a in due)


def test_get_critical_assets():
    registry = _registry()
    asset = _asset(registry)
    registry.update_asset(asset.asset_id, condition=AssetCondition.CRITICAL)
    critical = registry.get_critical_assets()
    assert any(a.asset_id == asset.asset_id for a in critical)


def test_create_saudi_fleet_template():
    registry = _registry()
    assets = registry.create_saudi_fleet_template()
    assert len(assets) == 20
    fighter_count = len([a for a in assets if a.asset_type == AssetType.FIGHTER_JET])
    assert fighter_count == 6
