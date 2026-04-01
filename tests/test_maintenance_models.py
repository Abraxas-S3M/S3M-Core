from __future__ import annotations

from datetime import datetime, timedelta, timezone

from services.maintenance.models import (
    Asset,
    AssetCondition,
    AssetStatus,
    AssetType,
    ProcurementRequest,
    ProcurementStatus,
    RULPrediction,
    SensorTelemetry,
    SparePartInventory,
    WorkOrder,
    WorkOrderPriority,
    WorkOrderStatus,
    MaintenanceType,
)


def _sample_asset() -> Asset:
    return Asset(
        asset_id="ast-1",
        name="F-15SA",
        designation="F-15SA #201",
        asset_type=AssetType.FIGHTER_JET,
        status=AssetStatus.OPERATIONAL,
        condition=AssetCondition.GOOD,
        serial_number="F15-201",
        manufacturer="S3M Aero",
        model="F-15SA",
        acquisition_date=datetime.now(timezone.utc) - timedelta(days=1000),
        last_maintenance=datetime.now(timezone.utc) - timedelta(days=10),
        next_maintenance=datetime.now(timezone.utc) + timedelta(days=5),
        operating_hours=3200.0,
        cycles=4200,
        location="Air Base",
        assigned_unit="RSAF",
    )


def test_asset_creation_and_methods():
    asset = _sample_asset()
    payload = asset.to_dict()
    assert payload["designation"] == "F-15SA #201"
    assert asset.days_since_maintenance() is not None
    assert asset.days_since_maintenance() >= 0
    assert asset.days_until_maintenance() is not None
    assert asset.is_due_for_maintenance() is False

    asset.condition = AssetCondition.CRITICAL
    assert asset.risk_level() == "critical"


def test_work_order_creation_and_duration():
    now = datetime.now(timezone.utc)
    wo = WorkOrder(
        work_order_id="wo-1",
        asset_id="ast-1",
        title="Engine Check",
        description="Predictive engine check",
        maintenance_type=MaintenanceType.PREDICTIVE,
        priority=WorkOrderPriority.URGENT,
        status=WorkOrderStatus.IN_PROGRESS,
        assigned_technician="tech-1",
        estimated_hours=6.0,
        parts_required=[],
        created_at=now,
        started_at=now - timedelta(hours=2),
        completed_at=now,
        cost_estimate=1000.0,
        actual_cost=1200.0,
        notes="done",
    )
    assert wo.is_open() is True
    assert wo.duration_hours() is not None
    assert wo.duration_hours() >= 1.9


def test_sensor_telemetry_feature_vector():
    telemetry = SensorTelemetry(
        asset_id="ast-1",
        timestamp=datetime.now(timezone.utc),
        readings={"temperature_c": 450, "vibration_g": 2.3, "state": "ok"},
        operating_mode="cruise",
    )
    features = telemetry.to_feature_vector()
    assert len(features) == 2


def test_rul_prediction_fields():
    prediction = RULPrediction(
        prediction_id="pred-1",
        asset_id="ast-1",
        timestamp=datetime.now(timezone.utc),
        rul_hours=145.0,
        confidence=0.83,
        model_used="rules",
        risk_level="high",
        failure_mode="bearing_degradation",
        sensor_features={"temperature_c_mean": 470.0},
        recommendation="Inspect bearing assembly",
    )
    payload = prediction.to_dict()
    assert payload["asset_id"] == "ast-1"
    assert payload["risk_level"] == "high"


def test_procurement_request_pending_and_age():
    req = ProcurementRequest(
        request_id="pr-1",
        asset_id="ast-1",
        work_order_id="wo-1",
        part_name="Bearing Kit",
        part_number="BRG-KIT-008",
        quantity=4,
        urgency=WorkOrderPriority.URGENT,
        status=ProcurementStatus.REQUESTED,
        supplier_id=None,
        estimated_cost=1200.0,
        requested_by="system",
        requested_at=datetime.now(timezone.utc) - timedelta(days=2),
    )
    assert req.is_pending() is True
    assert req.days_since_request() >= 1.9


def test_spare_part_reorder_logic():
    part = SparePartInventory(
        part_id="p-1",
        part_name="Seal Kit",
        part_number="SEAL-001",
        quantity_on_hand=5,
        reorder_threshold=6,
        reorder_quantity=20,
        unit_cost=55.0,
        location="Depot-1",
        compatible_assets=["FIGHTER_JET"],
    )
    assert part.needs_reorder() is True
