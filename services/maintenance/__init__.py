"""
S3M Layer 11 — Procurement & Maintenance
Predictive maintenance, asset lifecycle management, and procurement intelligence.

Subsystems:
- Predictive Engine: RUL estimation for aircraft engines, vehicles, naval systems
- Asset Manager: Military asset registry with lifecycle tracking
- Fleet Manager: Vehicle/aircraft/vessel fleet scheduling and health monitoring
- Procurement Tracker: Acquisition workflow, supplier management, restock triggers
- Maintenance Scheduler: Work order generation based on predictive + calendar triggers
- LLM Intelligence: Maintenance reports, procurement recommendations, failure analysis

Data Flow:
  Sensor telemetry → Predictive models → RUL estimates → Maintenance schedule
  → Procurement triggers when spares needed → LLM generates recommendations
  → Dashboard (Layer 06) shows fleet health + upcoming maintenance
"""

from services.maintenance.assets import AssetRegistry, ERPAdapter, FleetManager
from services.maintenance.manager import MaintenanceManager
from services.maintenance.models import (
    Asset,
    AssetCondition,
    AssetStatus,
    AssetType,
    FleetType,
    FleetVehicle,
    MaintenanceRecord,
    MaintenanceType,
    ProcurementRequest,
    ProcurementStatus,
    RULPrediction,
    SensorTelemetry,
    SparePartInventory,
    Supplier,
    WorkOrder,
    WorkOrderPriority,
    WorkOrderStatus,
)
from services.maintenance.predictive import PredictiveEngine
from services.maintenance.procurement import MaintenanceScheduler, ProcurementTracker

__all__ = [
    "MaintenanceManager",
    "Asset",
    "AssetType",
    "AssetStatus",
    "AssetCondition",
    "MaintenanceRecord",
    "MaintenanceType",
    "WorkOrder",
    "WorkOrderStatus",
    "WorkOrderPriority",
    "FleetVehicle",
    "FleetType",
    "RULPrediction",
    "SensorTelemetry",
    "ProcurementRequest",
    "ProcurementStatus",
    "Supplier",
    "SparePartInventory",
    "PredictiveEngine",
    "AssetRegistry",
    "FleetManager",
    "ProcurementTracker",
    "MaintenanceScheduler",
    "ERPAdapter",
]
