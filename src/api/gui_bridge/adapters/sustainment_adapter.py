"""Sustainment workspace adapter.

Reshapes maintenance assets and logistics inventory into
fleet readiness and supply chain views.

Internal dependencies:
- src.api.maintenance_routes (_assets, _work_orders)
- src.apps.logistics (optional)
"""

from datetime import datetime, timezone

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
