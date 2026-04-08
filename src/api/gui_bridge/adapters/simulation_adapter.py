"""Simulation workspace adapter — thin wrapper over simulation routes."""

from datetime import datetime, timezone
from typing import Any

from src.api.gui_bridge.models.gui_schemas import GUIScenario, GUISimulationData
from src.api.gui_bridge.training_emitter import emit_training_record


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class SimulationAdapter:
    def __init__(self):
        self._store = None
        self._use_store_scenarios = False
        try:
            from src.persistence.store_seeder import seed_store_if_empty

            self._store = seed_store_if_empty()
            self._use_store_scenarios = self._store.has_data("scenarios")
        except Exception:
            pass

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
            if scenarios:
                self._persist_rows("scenarios", scenarios)
            result = GUISimulationData(
                scenarios=scenarios or self._get_stored_or_default_scenarios(),
                updatedAt=_now_iso(),
            ).model_dump()
            emit_training_record("simulation", {"query": "scenarios"}, result)
            return result
        except Exception:
            result = GUISimulationData(
                scenarios=self._get_stored_or_default_scenarios(), updatedAt=_now_iso()
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

    def get_scenario_catalog(self) -> dict:
        """Pull from TrainingSimManager for full catalog."""
        try:
            from apps.simulation.manager import TrainingSimManager

            mgr = TrainingSimManager()
            catalog = (
                mgr.get_scenario_catalog()
                if hasattr(mgr, "get_scenario_catalog")
                else []
            )
            scenarios = [
                GUIScenario(
                    id=entry["id"],
                    name=entry["name"],
                    description=entry["description"],
                    status=entry["status"],
                    type=entry["type"],
                    updatedAt=entry["updatedAt"],
                ).model_dump()
                for entry in self._map_catalog(catalog)
            ]
            if scenarios:
                self._persist_rows("scenarios", scenarios)
            return GUISimulationData(
                scenarios=scenarios or self._get_stored_or_default_scenarios(),
                updatedAt=_now_iso(),
            ).model_dump()
        except Exception:
            return self.get_scenarios()

    def get_aar(self, scenario_id: str) -> dict:
        sid = str(scenario_id).strip() or "unknown"
        try:
            from src.validation.aar_recorder import AARRecorder

            recorder = AARRecorder()
            aar = recorder.get(sid) if hasattr(recorder, "get") else {}
            if hasattr(aar, "model_dump"):
                aar = aar.model_dump()
            elif hasattr(aar, "to_dict"):
                aar = aar.to_dict()
            if not isinstance(aar, dict):
                aar = {}
            return {"scenarioId": sid, "aar": aar, "updatedAt": _now_iso()}
        except Exception:
            return {"scenarioId": sid, "aar": {}, "updatedAt": _now_iso()}

    def run_comparison(self, scenario_id: str) -> dict:
        sid = str(scenario_id).strip() or "unknown"
        try:
            from apps.simulation.wargaming import WargameSuite

            suite = WargameSuite()
            comparison: dict[str, Any] = {
                "scenarioId": sid,
                "modes": {
                    "scripted": "available",
                    "llm": "available",
                },
            }
            if hasattr(suite, "get_statistics"):
                comparison["suiteStats"] = suite.get_statistics()
            return {"comparison": comparison, "updatedAt": _now_iso()}
        except Exception:
            return {"comparison": {}, "updatedAt": _now_iso()}

    def _map_catalog(self, catalog: Any) -> list[dict]:
        entries: list[Any]
        if isinstance(catalog, dict):
            if isinstance(catalog.get("scenarios"), list):
                entries = catalog["scenarios"]
            elif isinstance(catalog.get("catalog"), list):
                entries = catalog["catalog"]
            else:
                entries = []
        elif isinstance(catalog, list):
            entries = catalog
        else:
            entries = []

        mapped: list[dict] = []
        for idx, scenario in enumerate(entries):
            payload = (
                scenario
                if isinstance(scenario, dict)
                else (
                    scenario.model_dump()
                    if hasattr(scenario, "model_dump")
                    else (
                        scenario.to_dict()
                        if hasattr(scenario, "to_dict")
                        else {}
                    )
                )
            )
            if not isinstance(payload, dict):
                continue

            scenario_id = str(
                payload.get("id")
                or payload.get("scenario_id")
                or payload.get("wargame_id")
                or f"SCN-{idx + 1:03d}"
            ).strip()
            mapped.append(
                {
                    "id": scenario_id,
                    "name": str(payload.get("name") or scenario_id).strip(),
                    "description": str(payload.get("description", "")).strip(),
                    "status": str(payload.get("status", "ready")).strip() or "ready",
                    "type": str(
                        payload.get("type")
                        or payload.get("scenario_type")
                        or payload.get("wargame_type")
                        or "tactical"
                    ).strip(),
                    "updatedAt": str(
                        payload.get("updatedAt")
                        or payload.get("updated_at")
                        or _now_iso()
                    ),
                }
            )
        return mapped

    def _persist_rows(self, table: str, rows: list[dict]) -> None:
        if self._store is None:
            return
        for row in rows:
            if isinstance(row, dict):
                self._store.upsert(table, row)
        if table == "scenarios":
            self._use_store_scenarios = True

    def _get_stored_or_default_scenarios(self) -> list[dict]:
        if self._store is not None and self._use_store_scenarios:
            stored = self._store.get_all("scenarios")
            if stored:
                return stored
        defaults = self._defaults()
        self._persist_rows("scenarios", defaults)
        return defaults
