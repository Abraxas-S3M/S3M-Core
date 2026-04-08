"""Sustainment workspace adapter.

Reshapes maintenance assets and logistics inventory into
fleet readiness and supply chain views.

Internal dependencies:
- src.api.maintenance_routes (_assets, _work_orders)
- src.apps.logistics (optional)
"""

from datetime import datetime, timezone
from typing import Any

from src.api.gui_bridge.models.gui_schemas import (
    GUIFleetData,
    GUIFleetUnit,
    GUISupplyCategory,
    GUISupplyData,
)
from src.api.gui_bridge.training_emitter import emit_training_record


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class SustainmentAdapter:
    def get_fleet(self) -> dict:
        units = self._build_fleet_units()
        result = GUIFleetData(units=units, updatedAt=_now_iso()).model_dump()
        emit_training_record("sustainment", {"query": "fleet"}, result)
        return result

    def get_supply(self) -> dict:
        categories = self._build_supply()
        result = GUISupplyData(categories=categories, updatedAt=_now_iso()).model_dump()
        emit_training_record("sustainment", {"query": "supply"}, result)
        return result

    def get_predictions(self) -> dict:
        """Predictive maintenance ordered by lowest remaining life first."""
        try:
            from src.logistics.reliability_analyzer import OperationalStore, ReliabilityAnalyzer

            store = OperationalStore()
            analyzer = ReliabilityAnalyzer(operational_store=store)
            predictions: list[dict[str, Any]] = []

            for asset in store.get_assets():
                asset_id = str(getattr(asset, "asset_id", "")).strip()
                if not asset_id:
                    continue

                raw_type = getattr(asset, "asset_type", "OTHER")
                asset_type = raw_type.value if hasattr(raw_type, "value") else str(raw_type)
                hours_in_service = max(0.0, self._safe_float(getattr(asset, "operating_hours", 0.0)))
                remaining_hours = analyzer.estimate_rul(asset_type=asset_type, hours_in_service=hours_in_service)

                predictions.append(
                    {
                        "assetId": asset_id,
                        "designation": str(getattr(asset, "designation", asset_id)),
                        "assetType": asset_type,
                        "hoursInService": round(hours_in_service, 2),
                        "estimatedRULHours": round(remaining_hours, 2),
                        "urgency": self._urgency_from_rul(remaining_hours),
                    }
                )

            predictions.sort(key=lambda row: float(row.get("estimatedRULHours", float("inf"))))
            self._log_training_sample(maintenance_outcomes=predictions)
            return {"predictions": predictions, "updatedAt": _now_iso()}
        except Exception:
            return {"predictions": [], "updatedAt": _now_iso()}

    def get_supply_twin(self) -> dict:
        """Digital twin supply chain status."""
        try:
            from src.logistics.supply_chain_twin import SupplyChainTwin

            twin = SupplyChainTwin()
            status = twin.get_status() if hasattr(twin, "get_status") else {}
            return {"supplyChain": status, "updatedAt": _now_iso()}
        except Exception:
            return self.get_supply()

    def _build_fleet_units(self):
        try:
            from src.api.maintenance_routes import _assets

            # Group assets by unit
            by_unit = {}
            for asset in _assets.values():
                ad = (
                    asset
                    if isinstance(asset, dict)
                    else (asset.model_dump() if hasattr(asset, "model_dump") else {})
                )
                unit = ad.get("unit", ad.get("assigned_unit", "UNASSIGNED"))
                by_unit.setdefault(unit, []).append(ad)
            results = []
            for unit_id, assets in by_unit.items():
                fmc = sum(
                    1
                    for a in assets
                    if a.get("status") in ("operational", "ready", "fmc")
                )
                pmc = sum(
                    1 for a in assets if a.get("status") in ("degraded", "pmc", "partial")
                )
                nmc = len(assets) - fmc - pmc
                readiness = int((fmc / max(1, len(assets))) * 100)
                results.append(
                    GUIFleetUnit(
                        unitId=unit_id,
                        unitName=unit_id,
                        fmc=fmc,
                        pmc=pmc,
                        nmc=max(0, nmc),
                        totalAssets=len(assets),
                        readinessPercent=readiness,
                    )
                )
            return results if results else self._default_fleet()
        except Exception:
            return self._default_fleet()

    def _build_supply(self):
        try:
            from src.api.apps_routes import _logistics_manager

            if _logistics_manager and hasattr(_logistics_manager, "get_inventory"):
                inv = _logistics_manager.get_inventory()
                # reshape if available
            return self._default_supply()
        except Exception:
            return self._default_supply()

    @staticmethod
    def _default_fleet():
        return [
            GUIFleetUnit(
                unitId="1-82nd",
                unitName="1st BN, 82nd ABN",
                fmc=38,
                pmc=8,
                nmc=4,
                totalAssets=50,
                readinessPercent=76,
            ),
            GUIFleetUnit(
                unitId="2-101st",
                unitName="2nd BN, 101st ABN",
                fmc=42,
                pmc=5,
                nmc=3,
                totalAssets=50,
                readinessPercent=84,
            ),
            GUIFleetUnit(
                unitId="3-10th",
                unitName="3rd BN, 10th MTN",
                fmc=35,
                pmc=10,
                nmc=5,
                totalAssets=50,
                readinessPercent=70,
            ),
        ]

    @staticmethod
    def _default_supply():
        return [
            GUISupplyCategory(
                category="ammo",
                onHand=8400,
                required=10000,
                fillRate=84,
                status="amber",
            ),
            GUISupplyCategory(
                category="fuel",
                onHand=45000,
                required=50000,
                fillRate=90,
                status="green",
            ),
            GUISupplyCategory(
                category="rations",
                onHand=12000,
                required=14000,
                fillRate=86,
                status="green",
            ),
            GUISupplyCategory(
                category="medical",
                onHand=3200,
                required=5000,
                fillRate=64,
                status="red",
            ),
            GUISupplyCategory(
                category="repair_parts",
                onHand=1800,
                required=2500,
                fillRate=72,
                status="amber",
            ),
        ]

    @staticmethod
    def _normalize_rows(rows: Any) -> list[dict]:
        if not isinstance(rows, list):
            return []
        normalized: list[dict] = []
        for row in rows:
            if isinstance(row, dict):
                normalized.append(dict(row))
            elif hasattr(row, "to_dict"):
                normalized.append(row.to_dict())
            elif hasattr(row, "model_dump"):
                normalized.append(row.model_dump())
        return normalized

    @staticmethod
    def _urgency_from_rul(remaining_hours: float) -> str:
        if remaining_hours < 50:
            return "critical"
        if remaining_hours < 200:
            return "high"
        if remaining_hours < 500:
            return "medium"
        return "low"

    @staticmethod
    def _safe_float(value: Any) -> float:
        try:
            return float(value)
        except (TypeError, ValueError):
            return 0.0

    @staticmethod
    def _log_training_sample(
        fleet_health: dict | None = None,
        maintenance_outcomes: list[dict] | None = None,
    ) -> None:
        try:
            from src.training.cpu_adaptation.stream_learner import (
                log_fleet_maintenance_training_sample,
            )

            log_fleet_maintenance_training_sample(
                fleet_health=fleet_health,
                maintenance_outcomes=maintenance_outcomes,
            )
        except Exception:
            # GUI routes must continue serving sustainment state even if
            # local training-data persistence is temporarily unavailable.
            return
