"""Central manager for S3M Layer 11 procurement and maintenance."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import List

from services.maintenance.assets import AssetRegistry, ERPAdapter, FleetManager
from services.maintenance.models import (
    Asset,
    ProcurementRequest,
    RULPrediction,
    WorkOrder,
)
from services.maintenance.predictive import PredictiveEngine
from services.maintenance.procurement import MaintenanceScheduler, ProcurementTracker, SparePartsManager


class MaintenanceManager:
    """End-to-end orchestrator for predictive maintenance and procurement."""

    def __init__(self):
        self.predictive_engine = PredictiveEngine(model_backend="auto")
        self.asset_registry = AssetRegistry(max_assets=50000)
        self.fleet_manager = FleetManager(asset_registry=self.asset_registry, predictive_engine=self.predictive_engine)
        self.procurement_tracker = ProcurementTracker()
        self.spare_parts = SparePartsManager()
        self.maintenance_scheduler = MaintenanceScheduler(
            asset_registry=self.asset_registry,
            predictive_engine=self.predictive_engine,
            spare_parts=self.spare_parts,
        )
        self.erp_adapter = ERPAdapter(backend="auto")
        self.latest_predictions: dict[str, RULPrediction] = {}

    def ingest_telemetry(self, asset_id, readings, operating_mode) -> dict:
        return self.fleet_manager.ingest_telemetry(asset_id=asset_id, readings=readings, operating_mode=operating_mode)

    def predict_rul(self, asset_id) -> RULPrediction:
        asset = self.asset_registry.get_asset(asset_id)
        if asset is None:
            raise KeyError(f"Asset not found: {asset_id}")
        history = self.fleet_manager.telemetry_history.get(asset_id, [])
        prediction = self.predictive_engine.rul_estimator.predict(history, asset)
        self.asset_registry.update_rul(asset_id, prediction.rul_hours, prediction.confidence)
        self.latest_predictions[asset_id] = prediction
        return prediction

    def get_fleet_health(self) -> dict:
        health = self.fleet_manager.run_fleet_health_check()
        health["readiness"] = self.fleet_manager.get_fleet_readiness()
        return health

    def get_maintenance_schedule(self, days_ahead=30) -> List[dict]:
        return self.maintenance_scheduler.get_schedule(days_ahead=days_ahead)

    def generate_work_orders(self) -> List[WorkOrder]:
        return self.maintenance_scheduler.generate_work_orders(days_ahead=30)

    def check_procurement_needs(self) -> List[ProcurementRequest]:
        work_orders = self.maintenance_scheduler.get_work_orders()
        requests = self.procurement_tracker.auto_generate_from_work_orders(work_orders)
        reorder_parts = self.spare_parts.check_reorder()
        requests.extend(self.procurement_tracker.auto_generate_from_inventory(reorder_parts))
        for req in requests:
            self.erp_adapter.push_procurement_request(req)
        return requests

    def get_asset(self, asset_id):
        return self.asset_registry.get_asset(asset_id)

    def get_assets(self, **filters):
        return self.asset_registry.get_assets(**filters)

    def register_asset(self, **kwargs) -> Asset:
        return self.asset_registry.register(
            name=kwargs["name"],
            designation=kwargs["designation"],
            asset_type=kwargs["asset_type"],
            serial_number=kwargs["serial_number"],
            manufacturer=kwargs["manufacturer"],
            model=kwargs["model"],
            location=kwargs["location"],
            assigned_unit=kwargs["assigned_unit"],
            operating_hours=kwargs.get("operating_hours", 0.0),
        )

    def get_spare_parts(self):
        return self.spare_parts.get_parts()

    def get_procurement_requests(self):
        return self.procurement_tracker.get_requests()

    def generate_fleet_report(self) -> str:
        summary = self.asset_registry.get_fleet_summary()
        readiness = self.fleet_manager.get_fleet_readiness()
        procurement = self.procurement_tracker.get_stats()
        prompt = (
            "Generate a military fleet maintenance report: "
            f"{summary}. Include: 1) Overall readiness 2) Critical assets "
            f"3) Upcoming maintenance 4) Procurement needs 5) Recommendations."
        )
        try:
            from src.llm_core.inference import S3MInference

            text = S3MInference().generate(prompt, max_tokens=350)
            if isinstance(text, str) and text.strip():
                return text.strip()
        except Exception:
            pass

        # Tactical fallback report keeps command staff informed without external dependencies.
        lines = [
            "S3M Fleet Maintenance Report",
            f"Timestamp: {datetime.now(timezone.utc).isoformat()}",
            f"Overall Readiness: {readiness['readiness_pct']}% ({readiness['operational']}/{readiness['total_assets']})",
            f"Critical Assets: {', '.join(readiness['critical_assets']) if readiness['critical_assets'] else 'None'}",
            f"Maintenance Due: {summary['maintenance_due_count']}",
            f"Procurement Pending: {procurement['pending']}",
            "Recommendations: Prioritize EMERGENCY work orders, secure low-stock parts, and preserve combat sortie generation capacity.",
        ]
        return "\n".join(lines)

    def health_check(self) -> dict:
        return {
            "status": "operational",
            "predictive_engine": self.predictive_engine.health_check(),
            "asset_registry": self.asset_registry.get_fleet_summary(),
            "fleet_manager": self.fleet_manager.get_fleet_readiness(),
            "scheduler": self.maintenance_scheduler.get_stats(),
            "procurement": self.procurement_tracker.get_stats(),
            "spare_parts": self.spare_parts.get_stats(),
            "erp": self.erp_adapter.get_erp_status(),
        }
