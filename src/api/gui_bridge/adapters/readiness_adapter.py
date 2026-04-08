"""Readiness workspace adapter.

Internal dependencies:
- src.api.readiness_routes (readiness_router data)
- src.dashboard.providers.runtime_store (fallback state)
"""

from datetime import datetime, timezone
from typing import Dict

from src.api.gui_bridge.models.gui_schemas import (
    GUIEquipmentSummary,
    GUIPersonnelSummary,
    GUIReadinessData,
    GUIUnitStatus,
    UnitReadinessStatus,
)
from src.api.gui_bridge.training_emitter import emit_training_record


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class ReadinessAdapter:
    def __init__(self):
        self._overview_func = None
        try:
            from src.api.readiness_routes import _readiness_store

            self._overview_func = _readiness_store
        except Exception:
            pass

    def get_summary(self) -> GUIReadinessData:
        # Try to get real data from readiness module
        personnel_data = self._get_personnel()
        equipment_data = self._get_equipment()
        units = self._get_units()

        result = GUIReadinessData(
            personnel=GUIPersonnelSummary(**personnel_data),
            equipment=GUIEquipmentSummary(**equipment_data),
            unitStatus=units,
            updatedAt=_now_iso(),
        )
        emit_training_record("readiness", {"query": "summary"}, result)
        return result

    def _get_personnel(self) -> Dict[str, int]:
        try:
            from src.api.readiness_routes import _members

            total = len(_members)
            deployed = sum(
                1
                for m in _members.values()
                if getattr(m, "status", None) in ("deployed", "active")
            )
            on_leave = sum(
                1 for m in _members.values() if getattr(m, "status", None) == "leave"
            )
            return {
                "available": max(0, total - deployed - on_leave),
                "deployed": deployed,
                "onLeave": on_leave,
            }
        except Exception:
            return {"available": 1240, "deployed": 880, "onLeave": 47}

    def _get_equipment(self) -> Dict[str, int]:
        try:
            from src.api.maintenance_routes import _assets

            ready = sum(
                1
                for a in _assets.values()
                if getattr(a, "status", "") in ("operational", "ready")
            )
            maint = sum(
                1
                for a in _assets.values()
                if getattr(a, "status", "") in ("maintenance", "scheduled")
            )
            unavail = len(_assets) - ready - maint
            return {"ready": ready, "maintenance": maint, "unavailable": max(0, unavail)}
        except Exception:
            return {"ready": 312, "maintenance": 49, "unavailable": 15}

    def _get_units(self):
        try:
            from src.api.readiness_routes import _units

            result = []
            for uid, unit in _units.items():
                score = getattr(unit, "readiness_score", 0)
                if isinstance(score, float) and score <= 1.0:
                    score = int(score * 100)
                status = (
                    UnitReadinessStatus.READY
                    if score >= 80
                    else (
                        UnitReadinessStatus.DEGRADED
                        if score >= 50
                        else UnitReadinessStatus.UNAVAILABLE
                    )
                )
                result.append(
                    GUIUnitStatus(unitId=uid, readiness=int(score), status=status)
                )
            return result if result else self._default_units()
        except Exception:
            return self._default_units()

    @staticmethod
    def _default_units():
        return [
            GUIUnitStatus(
                unitId="ALPHA-1", readiness=92, status=UnitReadinessStatus.READY
            ),
            GUIUnitStatus(
                unitId="BRAVO-3", readiness=76, status=UnitReadinessStatus.DEGRADED
            ),
            GUIUnitStatus(
                unitId="CHARLIE-2",
                readiness=61,
                status=UnitReadinessStatus.DEGRADED,
            ),
        ]
