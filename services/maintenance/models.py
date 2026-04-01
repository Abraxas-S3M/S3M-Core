"""Data models for S3M Layer 11 procurement and maintenance workflows."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _dt(value: Optional[datetime]) -> Optional[datetime]:
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value


def _serialize(value: Any) -> Any:
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, list):
        return [_serialize(v) for v in value]
    if isinstance(value, dict):
        return {k: _serialize(v) for k, v in value.items()}
    return value


class AssetType(str, Enum):
    AIRCRAFT = "AIRCRAFT"
    HELICOPTER = "HELICOPTER"
    FIGHTER_JET = "FIGHTER_JET"
    TRANSPORT_AIRCRAFT = "TRANSPORT_AIRCRAFT"
    UAV = "UAV"
    GROUND_VEHICLE = "GROUND_VEHICLE"
    APC = "APC"
    TANK = "TANK"
    TRUCK = "TRUCK"
    NAVAL_VESSEL = "NAVAL_VESSEL"
    PATROL_BOAT = "PATROL_BOAT"
    FRIGATE = "FRIGATE"
    RADAR_SYSTEM = "RADAR_SYSTEM"
    COMM_SYSTEM = "COMM_SYSTEM"
    WEAPON_SYSTEM = "WEAPON_SYSTEM"
    GENERATOR = "GENERATOR"
    SENSOR_ARRAY = "SENSOR_ARRAY"
    OTHER = "OTHER"


class AssetStatus(str, Enum):
    OPERATIONAL = "OPERATIONAL"
    DEGRADED = "DEGRADED"
    IN_MAINTENANCE = "IN_MAINTENANCE"
    AWAITING_PARTS = "AWAITING_PARTS"
    DECOMMISSIONED = "DECOMMISSIONED"
    IN_TRANSIT = "IN_TRANSIT"
    STORED = "STORED"


class AssetCondition(str, Enum):
    EXCELLENT = "EXCELLENT"
    GOOD = "GOOD"
    FAIR = "FAIR"
    POOR = "POOR"
    CRITICAL = "CRITICAL"
    UNKNOWN = "UNKNOWN"


@dataclass
class Asset:
    asset_id: str
    name: str
    designation: str
    asset_type: AssetType
    status: AssetStatus
    condition: AssetCondition
    serial_number: str
    manufacturer: str
    model: str
    acquisition_date: datetime
    last_maintenance: Optional[datetime] = None
    next_maintenance: Optional[datetime] = None
    operating_hours: float = 0.0
    cycles: int = 0
    location: str = ""
    assigned_unit: str = ""
    rul_hours: Optional[float] = None
    rul_confidence: Optional[float] = None
    sensor_readings: List[dict] = field(default_factory=list)
    maintenance_history: List[str] = field(default_factory=list)
    procurement_alerts: List[str] = field(default_factory=list)
    metadata: dict = field(default_factory=dict)

    def __post_init__(self) -> None:
        self.asset_type = AssetType(self.asset_type)
        self.status = AssetStatus(self.status)
        self.condition = AssetCondition(self.condition)
        self.acquisition_date = _dt(self.acquisition_date) or _utcnow()
        self.last_maintenance = _dt(self.last_maintenance)
        self.next_maintenance = _dt(self.next_maintenance)
        self.operating_hours = float(self.operating_hours)
        self.cycles = int(self.cycles)
        self.sensor_readings = list(self.sensor_readings)[-10:]

    def to_dict(self) -> Dict[str, Any]:
        return _serialize(asdict(self))

    def days_since_maintenance(self) -> Optional[float]:
        if self.last_maintenance is None:
            return None
        return max(0.0, (_utcnow() - self.last_maintenance).total_seconds() / 86400.0)

    def days_until_maintenance(self) -> Optional[float]:
        if self.next_maintenance is None:
            return None
        return (self.next_maintenance - _utcnow()).total_seconds() / 86400.0

    def is_due_for_maintenance(self) -> bool:
        if self.next_maintenance is not None and self.next_maintenance <= _utcnow():
            return True
        if self.rul_hours is not None and self.rul_hours < 200.0:
            return True
        return self.condition in {AssetCondition.POOR, AssetCondition.CRITICAL}

    def risk_level(self) -> str:
        if self.condition == AssetCondition.CRITICAL:
            return "critical"
        if self.rul_hours is not None:
            if self.rul_hours < 50:
                return "critical"
            if self.rul_hours < 200:
                return "high"
            if self.rul_hours < 500:
                return "medium"
        if self.condition in {AssetCondition.POOR}:
            return "high"
        if self.condition in {AssetCondition.FAIR, AssetCondition.UNKNOWN}:
            return "medium"
        return "low"


class FleetType(str, Enum):
    AIR = "AIR"
    GROUND = "GROUND"
    NAVAL = "NAVAL"
    MIXED = "MIXED"


@dataclass
class FleetVehicle:
    asset_id: str
    fleet_type: FleetType
    callsign: str
    mission_ready: bool = True

    def to_dict(self) -> Dict[str, Any]:
        return _serialize(asdict(self))


class MaintenanceType(str, Enum):
    PREVENTIVE = "PREVENTIVE"
    CORRECTIVE = "CORRECTIVE"
    PREDICTIVE = "PREDICTIVE"
    CONDITION_BASED = "CONDITION_BASED"
    OVERHAUL = "OVERHAUL"
    INSPECTION = "INSPECTION"


class WorkOrderPriority(str, Enum):
    EMERGENCY = "EMERGENCY"
    URGENT = "URGENT"
    ROUTINE = "ROUTINE"
    SCHEDULED = "SCHEDULED"
    DEFERRED = "DEFERRED"


class WorkOrderStatus(str, Enum):
    DRAFT = "DRAFT"
    APPROVED = "APPROVED"
    IN_PROGRESS = "IN_PROGRESS"
    AWAITING_PARTS = "AWAITING_PARTS"
    COMPLETED = "COMPLETED"
    CANCELLED = "CANCELLED"


@dataclass
class WorkOrder:
    work_order_id: str
    asset_id: str
    title: str
    description: str
    maintenance_type: MaintenanceType
    priority: WorkOrderPriority
    status: WorkOrderStatus
    assigned_technician: Optional[str]
    estimated_hours: float
    parts_required: List[dict]
    created_at: datetime
    scheduled_date: Optional[datetime] = None
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    cost_estimate: float = 0.0
    actual_cost: Optional[float] = None
    notes: str = ""
    llm_recommendation: Optional[str] = None

    def __post_init__(self) -> None:
        self.maintenance_type = MaintenanceType(self.maintenance_type)
        self.priority = WorkOrderPriority(self.priority)
        self.status = WorkOrderStatus(self.status)
        self.created_at = _dt(self.created_at) or _utcnow()
        self.scheduled_date = _dt(self.scheduled_date)
        self.started_at = _dt(self.started_at)
        self.completed_at = _dt(self.completed_at)
        self.estimated_hours = float(self.estimated_hours)
        self.cost_estimate = float(self.cost_estimate)
        if self.actual_cost is not None:
            self.actual_cost = float(self.actual_cost)

    def to_dict(self) -> Dict[str, Any]:
        return _serialize(asdict(self))

    def is_open(self) -> bool:
        return self.status not in {WorkOrderStatus.COMPLETED, WorkOrderStatus.CANCELLED}

    def duration_hours(self) -> Optional[float]:
        if self.started_at is None or self.completed_at is None:
            return None
        return max(0.0, (self.completed_at - self.started_at).total_seconds() / 3600.0)


@dataclass
class MaintenanceRecord:
    record_id: str
    asset_id: str
    work_order_id: str
    maintenance_type: MaintenanceType
    description: str
    performed_by: str
    performed_at: datetime
    hours_at_maintenance: float
    parts_replaced: List[dict]
    cost: float
    next_recommended: Optional[datetime]
    condition_before: AssetCondition
    condition_after: AssetCondition

    def __post_init__(self) -> None:
        self.maintenance_type = MaintenanceType(self.maintenance_type)
        self.performed_at = _dt(self.performed_at) or _utcnow()
        self.next_recommended = _dt(self.next_recommended)
        self.condition_before = AssetCondition(self.condition_before)
        self.condition_after = AssetCondition(self.condition_after)
        self.hours_at_maintenance = float(self.hours_at_maintenance)
        self.cost = float(self.cost)

    def to_dict(self) -> Dict[str, Any]:
        return _serialize(asdict(self))


@dataclass
class SensorTelemetry:
    asset_id: str
    timestamp: datetime
    readings: dict
    operating_mode: str = "cruise"

    def __post_init__(self) -> None:
        self.timestamp = _dt(self.timestamp) or _utcnow()
        self.readings = dict(self.readings)
        self.operating_mode = str(self.operating_mode)

    def to_dict(self) -> Dict[str, Any]:
        return _serialize(asdict(self))

    def to_feature_vector(self) -> List[float]:
        numeric = []
        for key in sorted(self.readings.keys()):
            value = self.readings[key]
            if isinstance(value, (int, float)):
                numeric.append(float(value))
        return numeric


@dataclass
class RULPrediction:
    prediction_id: str
    asset_id: str
    timestamp: datetime
    rul_hours: float
    confidence: float
    model_used: str
    risk_level: str
    failure_mode: Optional[str]
    sensor_features: dict
    recommendation: str

    def __post_init__(self) -> None:
        self.timestamp = _dt(self.timestamp) or _utcnow()
        self.rul_hours = float(self.rul_hours)
        self.confidence = max(0.0, min(1.0, float(self.confidence)))

    def to_dict(self) -> Dict[str, Any]:
        return _serialize(asdict(self))


class ProcurementStatus(str, Enum):
    REQUESTED = "REQUESTED"
    APPROVED = "APPROVED"
    ORDERED = "ORDERED"
    SHIPPED = "SHIPPED"
    RECEIVED = "RECEIVED"
    CANCELLED = "CANCELLED"
    BACKORDERED = "BACKORDERED"


@dataclass
class ProcurementRequest:
    request_id: str
    asset_id: Optional[str]
    work_order_id: Optional[str]
    part_name: str
    part_number: str
    quantity: int
    urgency: WorkOrderPriority
    status: ProcurementStatus
    supplier_id: Optional[str]
    estimated_cost: float
    requested_by: str
    requested_at: datetime
    approved_at: Optional[datetime] = None
    expected_delivery: Optional[datetime] = None
    notes: str = ""

    def __post_init__(self) -> None:
        self.urgency = WorkOrderPriority(self.urgency)
        self.status = ProcurementStatus(self.status)
        self.quantity = int(self.quantity)
        self.estimated_cost = float(self.estimated_cost)
        self.requested_at = _dt(self.requested_at) or _utcnow()
        self.approved_at = _dt(self.approved_at)
        self.expected_delivery = _dt(self.expected_delivery)

    def to_dict(self) -> Dict[str, Any]:
        return _serialize(asdict(self))

    def is_pending(self) -> bool:
        return self.status not in {ProcurementStatus.RECEIVED, ProcurementStatus.CANCELLED}

    def days_since_request(self) -> float:
        return max(0.0, (_utcnow() - self.requested_at).total_seconds() / 86400.0)


@dataclass
class Supplier:
    supplier_id: str
    name: str
    country: str
    capabilities: List[str]
    lead_time_days: float
    reliability_score: float
    contact: dict

    def __post_init__(self) -> None:
        self.lead_time_days = float(self.lead_time_days)
        self.reliability_score = max(0.0, min(1.0, float(self.reliability_score)))

    def to_dict(self) -> Dict[str, Any]:
        return _serialize(asdict(self))


@dataclass
class SparePartInventory:
    part_id: str
    part_name: str
    part_number: str
    quantity_on_hand: int
    reorder_threshold: int
    reorder_quantity: int
    unit_cost: float
    location: str
    compatible_assets: List[str]
    last_restock: Optional[datetime] = None

    def __post_init__(self) -> None:
        self.quantity_on_hand = int(self.quantity_on_hand)
        self.reorder_threshold = int(self.reorder_threshold)
        self.reorder_quantity = int(self.reorder_quantity)
        self.unit_cost = float(self.unit_cost)
        self.last_restock = _dt(self.last_restock)

    def to_dict(self) -> Dict[str, Any]:
        return _serialize(asdict(self))

    def needs_reorder(self) -> bool:
        return self.quantity_on_hand <= self.reorder_threshold
