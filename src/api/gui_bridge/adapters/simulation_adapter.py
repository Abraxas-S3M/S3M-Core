"""Simulation workspace adapter — thin wrapper over simulation routes."""

from datetime import datetime, timezone

from src.api.gui_bridge.models.gui_schemas import GUIScenario, GUISimulationData
from src.api.gui_bridge.training_emitter import emit_training_record


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class SimulationAdapter:
    def get_scenarios(self) -> dict:
        try:
            from src.api.simulation_routes import _scenario_store

            scenarios = []
            for sid, s in (_scenario_store or {}).items():
                sd = (
                    s
                    if isinstance(s, dict)
                    else (s.model_dump() if hasattr(s, "model_dump") else {})
                )
                scenarios.append(
                    GUIScenario(
                        id=sid,
                        name=sd.get("name", sid),
                        description=sd.get("description", ""),
                        status=sd.get("status", "ready"),
                        type=sd.get("type", "tactical"),
                        updatedAt=sd.get("updated_at", _now_iso()),
                    ).model_dump()
                )
            result = GUISimulationData(
                scenarios=scenarios or self._defaults(), updatedAt=_now_iso()
            ).model_dump()
            emit_training_record("simulation", {"query": "scenarios"}, result)
            return result
        except Exception:
            result = GUISimulationData(
                scenarios=self._defaults(), updatedAt=_now_iso()
            ).model_dump()
            emit_training_record("simulation", {"query": "scenarios"}, result)
            return result

    @staticmethod
    def _defaults():
        return [
            GUIScenario(
                id="SCN-001",
                name="Desert Shield Redux",
                description="Multi-domain force-on-force",
                status="ready",
                type="wargame",
            ).model_dump(),
            GUIScenario(
                id="SCN-002",
                name="Cyber Breach Response",
                description="SOC incident response drill",
                status="ready",
                type="cyber",
            ).model_dump(),
            GUIScenario(
                id="SCN-003",
                name="Maritime Interdiction",
                description="Strait chokepoint scenario",
                status="running",
                type="tactical",
            ).model_dump(),
        ]
