"""FastAPI routes for S3M Phase 17 procurement and maintenance layer."""

from __future__ import annotations

from typing import Dict, List, Optional

from fastapi import APIRouter, HTTPException, Query

from services.maintenance import (
    AssetCondition,
    AssetStatus,
    AssetType,
    MaintenanceManager,
    ProcurementStatus,
    WorkOrderPriority,
    WorkOrderStatus,
)
from src.api.maintenance_models import (
    AssetQueryParams,
    AssetResponse,
    ConditionReportResponse,
    FleetHealthResponse,
    FleetReadinessResponse,
    FleetReportResponse,
    IngestTelemetryRequest,
    MaintenanceScheduleResponse,
    ProcurementRequestCreate,
    ProcurementResponse,
    RegisterAssetRequest,
    RULPredictionResponse,
    SparePartCreateRequest,
    SparePartResponse,
    TelemetryResponse,
    WorkOrderUpdateRequest,
    WorkOrderResponse,
)


maintenance_router = APIRouter()
_maintenance = MaintenanceManager()


def _asset_to_response(asset) -> AssetResponse:
    return AssetResponse(**asset.to_dict())


def _work_order_to_response(work_order) -> WorkOrderResponse:
    return WorkOrderResponse(**work_order.to_dict())


def _procurement_to_response(request) -> ProcurementResponse:
    return ProcurementResponse(**request.to_dict())


@maintenance_router.post("/maintenance/assets", response_model=AssetResponse)
async def register_asset(req: RegisterAssetRequest) -> AssetResponse:
    try:
        asset = _maintenance.register_asset(
            name=req.name,
            designation=req.designation,
            asset_type=req.asset_type,
            serial_number=req.serial_number,
            manufacturer=req.manufacturer,
            model=req.model,
            location=req.location,
            assigned_unit=req.unit,
            operating_hours=req.hours,
        )
        return _asset_to_response(asset)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@maintenance_router.get("/maintenance/assets", response_model=List[AssetResponse])
async def list_assets(
    asset_type: Optional[AssetType] = Query(default=None, alias="type"),
    status: Optional[AssetStatus] = Query(default=None),
    condition: Optional[AssetCondition] = Query(default=None),
    location: Optional[str] = Query(default=None),
    unit: Optional[str] = Query(default=None),
    limit: int = Query(default=200, ge=1, le=50000),
) -> List[AssetResponse]:
    _ = AssetQueryParams(asset_type=asset_type, status=status, condition=condition, location=location, limit=limit)
    assets = _maintenance.get_assets(
        asset_type=asset_type.value if asset_type else None,
        status=status.value if status else None,
        condition=condition.value if condition else None,
        location=location,
        assigned_unit=unit,
    )
    return [_asset_to_response(asset) for asset in assets[:limit]]


@maintenance_router.get("/maintenance/assets/critical", response_model=List[AssetResponse])
async def list_critical_assets() -> List[AssetResponse]:
    rows = _maintenance.asset_registry.get_critical_assets()
    return [_asset_to_response(asset) for asset in rows]


@maintenance_router.get("/maintenance/assets/due", response_model=List[AssetResponse])
async def list_due_assets() -> List[AssetResponse]:
    rows = _maintenance.asset_registry.get_due_for_maintenance()
    return [_asset_to_response(asset) for asset in rows]


@maintenance_router.post("/maintenance/assets/template/saudi")
async def create_saudi_template() -> dict:
    rows = _maintenance.asset_registry.create_saudi_fleet_template()
    return {"count": len(rows), "assets": [asset.to_dict() for asset in rows]}


@maintenance_router.get("/maintenance/assets/{asset_id}", response_model=AssetResponse)
async def get_asset(asset_id: str) -> AssetResponse:
    asset = _maintenance.get_asset(asset_id)
    if asset is None:
        raise HTTPException(status_code=404, detail=f"Asset not found: {asset_id}")
    return _asset_to_response(asset)


@maintenance_router.post("/maintenance/telemetry", response_model=TelemetryResponse)
async def ingest_telemetry(req: IngestTelemetryRequest) -> TelemetryResponse:
    try:
        out = _maintenance.ingest_telemetry(req.asset_id, req.readings, req.operating_mode)
        return TelemetryResponse(**out)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@maintenance_router.post("/maintenance/predict/{asset_id}", response_model=RULPredictionResponse)
async def predict_asset_rul(asset_id: str) -> RULPredictionResponse:
    try:
        prediction = _maintenance.predict_rul(asset_id)
        return RULPredictionResponse(**prediction.to_dict())
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@maintenance_router.get("/maintenance/predict/{asset_id}", response_model=RULPredictionResponse)
async def get_latest_prediction(asset_id: str) -> RULPredictionResponse:
    prediction = _maintenance.latest_predictions.get(asset_id)
    if prediction is None:
        raise HTTPException(status_code=404, detail=f"No prediction found for asset: {asset_id}")
    return RULPredictionResponse(**prediction.to_dict())


@maintenance_router.post("/maintenance/work-orders/generate", response_model=List[WorkOrderResponse])
async def generate_work_orders() -> List[WorkOrderResponse]:
    rows = _maintenance.generate_work_orders()
    return [_work_order_to_response(row) for row in rows]


@maintenance_router.get("/maintenance/work-orders", response_model=List[WorkOrderResponse])
async def list_work_orders(
    status: Optional[WorkOrderStatus] = Query(default=None),
    priority: Optional[WorkOrderPriority] = Query(default=None),
    asset_id: Optional[str] = Query(default=None),
) -> List[WorkOrderResponse]:
    rows = _maintenance.maintenance_scheduler.get_work_orders(
        status=status.value if status else None,
        priority=priority.value if priority else None,
        asset_id=asset_id,
    )
    return [_work_order_to_response(row) for row in rows]


@maintenance_router.patch("/maintenance/work-orders/{work_order_id}", response_model=WorkOrderResponse)
async def update_work_order(work_order_id: str, req: WorkOrderUpdateRequest) -> WorkOrderResponse:
    try:
        scheduler = _maintenance.maintenance_scheduler
        action = req.action.lower()
        if action == "approve":
            scheduler.approve_work_order(work_order_id, req.approved_by or "api")
        elif action == "start":
            scheduler.start_work_order(work_order_id, req.technician or "api-tech")
        elif action == "complete":
            scheduler.complete_work_order(
                work_order_id,
                notes=req.notes or "Completed by API",
                parts_used=req.parts_used,
                cost=req.cost,
            )
        else:
            raise HTTPException(status_code=400, detail="action must be one of: approve|start|complete")
        wo = scheduler.work_orders[work_order_id]
        return _work_order_to_response(wo)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@maintenance_router.get("/maintenance/schedule", response_model=MaintenanceScheduleResponse)
async def get_schedule(days_ahead: int = Query(default=30, ge=1, le=365)) -> MaintenanceScheduleResponse:
    schedule = _maintenance.get_maintenance_schedule(days_ahead=days_ahead)
    return MaintenanceScheduleResponse(days_ahead=days_ahead, schedule=schedule)


@maintenance_router.post("/maintenance/procurement/check", response_model=List[ProcurementResponse])
async def check_procurement() -> List[ProcurementResponse]:
    rows = _maintenance.check_procurement_needs()
    return [_procurement_to_response(row) for row in rows]


@maintenance_router.get("/maintenance/procurement/requests", response_model=List[ProcurementResponse])
async def list_procurement_requests(
    status: Optional[ProcurementStatus] = Query(default=None),
    urgency: Optional[WorkOrderPriority] = Query(default=None),
    asset_id: Optional[str] = Query(default=None),
) -> List[ProcurementResponse]:
    rows = _maintenance.procurement_tracker.get_requests(
        status=status.value if status else None,
        urgency=urgency.value if urgency else None,
        asset_id=asset_id,
    )
    return [_procurement_to_response(row) for row in rows]


@maintenance_router.patch("/maintenance/procurement/requests/{request_id}", response_model=ProcurementResponse)
async def update_procurement_request(request_id: str, payload: Dict[str, str]) -> ProcurementResponse:
    req = _maintenance.procurement_tracker.get_request(request_id)
    if req is None:
        raise HTTPException(status_code=404, detail=f"Procurement request not found: {request_id}")
    try:
        status = payload.get("status")
        notes = payload.get("notes", "")
        if not status:
            raise HTTPException(status_code=400, detail="status is required")
        _maintenance.procurement_tracker.update_status(request_id, ProcurementStatus(status), notes=notes)
        req = _maintenance.procurement_tracker.get_request(request_id)
        return _procurement_to_response(req)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@maintenance_router.get("/maintenance/parts", response_model=List[SparePartResponse])
async def list_spare_parts() -> List[SparePartResponse]:
    rows = _maintenance.get_spare_parts()
    return [SparePartResponse(**row.to_dict()) for row in rows]


@maintenance_router.post("/maintenance/parts", response_model=SparePartResponse)
async def add_spare_part(req: SparePartCreateRequest) -> SparePartResponse:
    part = _maintenance.spare_parts.add_part(
        part_name=req.part_name,
        part_number=req.part_number,
        quantity=req.quantity,
        reorder_threshold=req.reorder_threshold,
        reorder_quantity=req.reorder_quantity,
        unit_cost=req.unit_cost,
        location=req.location,
        compatible_assets=req.compatible_assets,
    )
    return SparePartResponse(**part.to_dict())


@maintenance_router.get("/maintenance/parts/reorder", response_model=List[SparePartResponse])
async def list_reorder_parts() -> List[SparePartResponse]:
    rows = _maintenance.spare_parts.check_reorder()
    return [SparePartResponse(**row.to_dict()) for row in rows]


@maintenance_router.get("/maintenance/fleet/health", response_model=FleetHealthResponse)
async def fleet_health() -> FleetHealthResponse:
    data = _maintenance.get_fleet_health()
    return FleetHealthResponse(**data)


@maintenance_router.get("/maintenance/fleet/readiness", response_model=FleetReadinessResponse)
async def fleet_readiness() -> FleetReadinessResponse:
    data = _maintenance.fleet_manager.get_fleet_readiness()
    return FleetReadinessResponse(**data)


@maintenance_router.post("/maintenance/fleet/report", response_model=FleetReportResponse)
async def fleet_report() -> FleetReportResponse:
    report = _maintenance.generate_fleet_report()
    return FleetReportResponse(report=report)


@maintenance_router.get("/maintenance/condition/{asset_id}", response_model=ConditionReportResponse)
async def condition_report(asset_id: str) -> ConditionReportResponse:
    asset = _maintenance.get_asset(asset_id)
    if asset is None:
        raise HTTPException(status_code=404, detail=f"Asset not found: {asset_id}")
    history = _maintenance.fleet_manager.telemetry_history.get(asset_id, [])
    report = _maintenance.predictive_engine.condition_monitor.generate_condition_report(asset, history)
    return ConditionReportResponse(asset_id=asset_id, report=report)


@maintenance_router.get("/maintenance/status")
async def maintenance_status() -> dict:
    return _maintenance.health_check()
