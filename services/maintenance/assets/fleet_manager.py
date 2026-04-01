"""Fleet-level telemetry ingestion and readiness orchestration."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Dict, List

from services.maintenance.assets.asset_registry import AssetRegistry
from services.maintenance.models import AssetCondition, AssetStatus, SensorTelemetry
from services.maintenance.predictive import PredictiveEngine


class FleetManager:
    """Maintain near-real-time fleet health for tactical operations."""

    def __init__(self, asset_registry: AssetRegistry = None, predictive_engine: object = None):
        self.asset_registry = asset_registry or AssetRegistry()
        self.predictive_engine = predictive_engine or PredictiveEngine()
        self.telemetry_history: Dict[str, List[SensorTelemetry]] = {}
        self.latest_predictions: Dict[str, dict] = {}

    def ingest_telemetry(self, asset_id: str, readings: dict, operating_mode: str = "cruise") -> dict:
        asset = self.asset_registry.get_asset(asset_id)
        if asset is None:
            raise KeyError(f"Asset not found: {asset_id}")

        telemetry = SensorTelemetry(
            asset_id=asset_id,
            timestamp=datetime.now(timezone.utc),
            readings=dict(readings),
            operating_mode=operating_mode,
        )
        history = self.telemetry_history.setdefault(asset_id, [])
        history.append(telemetry)
        if len(history) > 500:
            self.telemetry_history[asset_id] = history[-500:]
            history = self.telemetry_history[asset_id]

        previous_condition = asset.condition
        condition_eval = self.predictive_engine.condition_monitor.evaluate(telemetry)
        new_condition = condition_eval["condition"]
        self.asset_registry.update_condition(asset_id, new_condition)

        asset.sensor_readings.append(telemetry.to_dict())
        asset.sensor_readings = asset.sensor_readings[-10:]
        condition_changed = previous_condition != new_condition

        rul_hours = asset.rul_hours
        if len(history) >= 10:
            prediction = self.predictive_engine.rul_estimator.predict(telemetry_history=history, asset=asset)
            self.latest_predictions[asset_id] = prediction.to_dict()
            rul_hours = prediction.rul_hours
            self.asset_registry.update_rul(asset_id, prediction.rul_hours, prediction.confidence)
            if prediction.risk_level in {"critical", "high"} and asset.status == AssetStatus.OPERATIONAL:
                asset.status = AssetStatus.DEGRADED

        alerts = list(condition_eval["alerts"])
        if condition_changed and new_condition == AssetCondition.CRITICAL:
            alerts.append(
                {
                    "sensor": "fleet_manager",
                    "value": new_condition.value,
                    "threshold": "CRITICAL",
                    "severity": "critical",
                    "message": f"Asset {asset.designation} entered CRITICAL condition",
                }
            )

        return {
            "asset_id": asset_id,
            "condition": new_condition.value,
            "rul_hours": rul_hours,
            "alerts": alerts,
            "condition_changed": condition_changed,
        }

    def run_fleet_health_check(self) -> dict:
        assets = self.asset_registry.get_assets()
        if not assets:
            return {
                "total_assets": 0,
                "readiness_score": 0.0,
                "assets_needing_attention": [],
                "upcoming_maintenance": [],
            }

        operational = [a for a in assets if a.status == AssetStatus.OPERATIONAL]
        readiness = (len(operational) / len(assets)) * 100.0
        attention = [
            {
                "asset_id": a.asset_id,
                "designation": a.designation,
                "condition": a.condition.value,
                "rul_hours": a.rul_hours,
            }
            for a in assets
            if a.condition in {AssetCondition.POOR, AssetCondition.CRITICAL} or (a.rul_hours is not None and a.rul_hours < 200)
        ]

        horizon = datetime.now(timezone.utc) + timedelta(days=30)
        upcoming = [
            {
                "asset_id": a.asset_id,
                "designation": a.designation,
                "next_maintenance": a.next_maintenance.isoformat() if a.next_maintenance else None,
            }
            for a in assets
            if a.next_maintenance is not None and a.next_maintenance <= horizon
        ]

        return {
            "total_assets": len(assets),
            "readiness_score": round(readiness, 2),
            "assets_needing_attention": attention,
            "upcoming_maintenance": upcoming,
        }

    def generate_maintenance_schedule(self, days_ahead: int = 30) -> List[dict]:
        now = datetime.now(timezone.utc)
        horizon = now + timedelta(days=int(days_ahead))
        recommendations: List[dict] = []

        for asset in self.asset_registry.get_assets():
            if asset.next_maintenance and asset.next_maintenance <= horizon:
                recommendations.append(
                    {
                        "asset_id": asset.asset_id,
                        "designation": asset.designation,
                        "reason": "calendar_due",
                        "priority": "ROUTINE",
                        "date": max(now, asset.next_maintenance).isoformat(),
                    }
                )
            if asset.rul_hours is not None and asset.rul_hours < 200:
                recommendations.append(
                    {
                        "asset_id": asset.asset_id,
                        "designation": asset.designation,
                        "reason": "predictive_rul",
                        "priority": "URGENT" if asset.rul_hours >= 50 else "EMERGENCY",
                        "date": now.isoformat(),
                    }
                )
            if asset.condition in {AssetCondition.POOR, AssetCondition.CRITICAL}:
                recommendations.append(
                    {
                        "asset_id": asset.asset_id,
                        "designation": asset.designation,
                        "reason": "condition_trigger",
                        "priority": "EMERGENCY" if asset.condition == AssetCondition.CRITICAL else "URGENT",
                        "date": now.isoformat(),
                    }
                )

        order = {"EMERGENCY": 0, "URGENT": 1, "ROUTINE": 2, "SCHEDULED": 3, "DEFERRED": 4}
        recommendations.sort(key=lambda item: (order.get(item["priority"], 99), item["date"]))
        return recommendations

    def get_fleet_readiness(self) -> dict:
        assets = self.asset_registry.get_assets()
        total = len(assets)
        operational = len([a for a in assets if a.status == AssetStatus.OPERATIONAL])
        readiness = (operational / total) * 100.0 if total else 0.0
        critical_assets = [a.designation for a in self.asset_registry.get_critical_assets()]
        maintenance_backlog = len(self.asset_registry.get_due_for_maintenance())
        return {
            "total_assets": total,
            "operational": operational,
            "readiness_pct": round(readiness, 2),
            "critical_assets": critical_assets,
            "maintenance_backlog": maintenance_backlog,
        }
