"""Pydantic schemas for Layer 11 procurement and maintenance API endpoints."""

from __future__ import annotations

from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, Field


class RegisterAssetRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=128)
    designation: str = Field(..., min_length=1, max_length=128)
    asset_type: str = Field(..., min_length=1, max_length=64)
    serial_number: str = Field(..., min_length=1, max_length=128)
    manufacturer: str = Field(..., min_length=1, max_length=128)
    model: str = Field(..., min_length=1, max_length=128)
    location: str = Field(..., min_length=1, max_length=128)
    unit: str = Field(..., min_length=1, max_length=128)
    hours: float = Field(default=0.0, ge=0.0)


class AssetResponse(BaseModel):
    asset_id: str
    name: str
    designation: str
    asset_type: str
    status: str
    condition: str
    serial_number: str
    manufacturer: str
    model: str
    acquisition_date: str
    last_maintenance: Optional[str] = None
    next_maintenance: Optional[str] = None
    operating_hours: float
    cycles: int
    location: str
    assigned_unit: str
    rul_hours: Optional[float] = None
    rul_confidence: Optional[float] = None
    sensor_readings: List[Dict[str, Any]] = Field(default_factory=list)
    maintenance_history: List[str] = Field(default_factory=list)
    procurement_alerts: List[str] = Field(default_factory=list)
    metadata: Dict[str, Any] = Field(default_factory=dict)


class IngestTelemetryRequest(BaseModel):
    asset_id: str = Field(..., min_length=1)
    readings: Dict[str, float] = Field(default_factory=dict)
    operating_mode: str = Field(default="cruise", min_length=1, max_length=32)


class TelemetryResponse(BaseModel):
    asset_id: str
    condition: str
    rul_hours: Optional[float] = None
    alerts: List[Dict[str, Any]] = Field(default_factory=list)
    condition_changed: bool


class RULPredictionResponse(BaseModel):
    prediction_id: str
    asset_id: str
    timestamp: str
    rul_hours: float
    confidence: float
    model_used: str
    risk_level: str
    failure_mode: Optional[str] = None
    sensor_features: Dict[str, float] = Field(default_factory=dict)
    recommendation: str


class ConditionReportResponse(BaseModel):
    asset_id: str
    report: str


class WorkOrderCreateRequest(BaseModel):
    asset_id: str = Field(..., min_length=1)
    title: str = Field(..., min_length=1, max_length=256)
    description: str = Field(..., min_length=1, max_length=2048)
    maintenance_type: str = Field(default="PREVENTIVE", min_length=1, max_length=64)
    priority: str = Field(default="ROUTINE", min_length=1, max_length=64)
    estimated_hours: float = Field(default=8.0, ge=0.0)
    parts_required: List[Dict[str, Any]] = Field(default_factory=list)


class WorkOrderUpdateRequest(BaseModel):
    action: Literal["approve", "start", "complete"]
    approved_by: Optional[str] = None
    technician: Optional[str] = None
    notes: str = ""
    parts_used: List[Dict[str, Any]] = Field(default_factory=list)
    cost: float = Field(default=0.0, ge=0.0)


class WorkOrderResponse(BaseModel):
    work_order_id: str
    asset_id: str
    title: str
    description: str
    maintenance_type: str
    priority: str
    status: str
    assigned_technician: Optional[str] = None
    estimated_hours: float
    parts_required: List[Dict[str, Any]]
    created_at: str
    scheduled_date: Optional[str] = None
    started_at: Optional[str] = None
    completed_at: Optional[str] = None
    cost_estimate: float
    actual_cost: Optional[float] = None
    notes: str
    llm_recommendation: Optional[str] = None


class ProcurementRequestCreate(BaseModel):
    part_name: str = Field(..., min_length=1, max_length=128)
    part_number: str = Field(..., min_length=1, max_length=128)
    quantity: int = Field(..., ge=1)
    urgency: str = Field(default="ROUTINE", min_length=1, max_length=64)
    asset_id: Optional[str] = None
    work_order_id: Optional[str] = None
    supplier_id: Optional[str] = None
    estimated_cost: float = Field(default=0.0, ge=0.0)
    requested_by: str = Field(default="system", min_length=1, max_length=64)


class ProcurementStatusUpdateRequest(BaseModel):
    status: str = Field(..., min_length=1, max_length=64)
    notes: str = ""


class ProcurementResponse(BaseModel):
    request_id: str
    asset_id: Optional[str] = None
    work_order_id: Optional[str] = None
    part_name: str
    part_number: str
    quantity: int
    urgency: str
    status: str
    supplier_id: Optional[str] = None
    estimated_cost: float
    requested_by: str
    requested_at: str
    approved_at: Optional[str] = None
    expected_delivery: Optional[str] = None
    notes: str


class SparePartCreateRequest(BaseModel):
    part_name: str = Field(..., min_length=1, max_length=128)
    part_number: str = Field(..., min_length=1, max_length=128)
    quantity: int = Field(..., ge=0)
    reorder_threshold: int = Field(..., ge=0)
    reorder_quantity: int = Field(..., ge=1)
    unit_cost: float = Field(..., ge=0.0)
    location: str = Field(..., min_length=1, max_length=128)
    compatible_assets: List[str] = Field(default_factory=list)


class SparePartResponse(BaseModel):
    part_id: str
    part_name: str
    part_number: str
    quantity_on_hand: int
    reorder_threshold: int
    reorder_quantity: int
    unit_cost: float
    location: str
    compatible_assets: List[str]
    last_restock: Optional[str] = None


class FleetHealthResponse(BaseModel):
    total_assets: int
    readiness_score: float
    assets_needing_attention: List[Dict[str, Any]] = Field(default_factory=list)
    upcoming_maintenance: List[Dict[str, Any]] = Field(default_factory=list)
    readiness: Dict[str, Any] = Field(default_factory=dict)


class FleetReadinessResponse(BaseModel):
    total_assets: int
    operational: int
    readiness_pct: float
    critical_assets: List[str]
    maintenance_backlog: int


class MaintenanceScheduleResponse(BaseModel):
    schedule: List[Dict[str, Any]]
    days_ahead: int


class FleetReportResponse(BaseModel):
    report: str


class AssetQueryParams(BaseModel):
    asset_type: Optional[str] = None
    status: Optional[str] = None
    condition: Optional[str] = None
    location: Optional[str] = None
    limit: int = Field(default=100, ge=1, le=5000)
