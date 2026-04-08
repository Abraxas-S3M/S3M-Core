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

    def run_ai_vs_human(self, scenario_id: str) -> dict:
        sid = str(scenario_id).strip() or "unknown"
        env = None
        try:
            import numpy as np

            from src.simulation.gym_wargame_env import (
                ACTION_ENGAGE,
                ACTION_HOLD,
                ACTION_MOVE,
                WargameEnv,
            )

            env = WargameEnv(scenario_id=sid)

            def _active_unit_count(observation: dict[str, Any]) -> int:
                health = np.asarray(observation.get("unit_health", []), dtype=np.float32)
                return int(np.count_nonzero(health > 0.0))

            def _rl_policy(observation: dict[str, Any]) -> Any:
                actions = np.full((env.max_units,), ACTION_HOLD, dtype=np.int64)
                active = _active_unit_count(observation)
                threat_levels = np.asarray(observation.get("threat_levels", []), dtype=np.float32)
                should_engage = bool(np.any(threat_levels > 0.0))
                for idx in range(min(active, env.max_units)):
                    actions[idx] = ACTION_ENGAGE if should_engage else ACTION_MOVE
                return actions

            def _scripted_human_baseline(observation: dict[str, Any]) -> Any:
                actions = np.full((env.max_units,), ACTION_HOLD, dtype=np.int64)
                active = _active_unit_count(observation)
                # Tactical context: this scripted baseline mimics a cautious human commander advancing by doctrine.
                for idx in range(min(active, env.max_units)):
                    actions[idx] = ACTION_MOVE
                return actions

            def _run_episode(policy_name: str, policy_fn) -> dict[str, Any]:
                observation, _ = env.reset(options={"scenario_id": sid})
                terminated = False
                truncated = False
                total_reward = 0.0
                last_info: dict[str, Any] = {}

                while not (terminated or truncated):
                    actions = policy_fn(observation)
                    observation, reward, terminated, truncated, last_info = env.step(actions)
                    total_reward += float(reward)

                return {
                    "name": policy_name,
                    "totalReward": round(total_reward, 3),
                    "steps": int(last_info.get("step", 0)),
                    "objectivesMet": len(last_info.get("objectives_met", [])),
                    "friendlyLosses": int(last_info.get("friendly_losses", 0)),
                    "episodeTuples": env.get_episode_tuples(),
                }

            ai_metrics = _run_episode("rl_agent", _rl_policy)
            baseline_metrics = _run_episode("scripted_human_baseline", _scripted_human_baseline)

            comparison = {
                "scenarioId": sid,
                "modes": {
                    "ai": "rl_agent",
                    "human": "scripted_human_baseline",
                },
                "ai": {k: v for k, v in ai_metrics.items() if k != "episodeTuples"},
                "human": {k: v for k, v in baseline_metrics.items() if k != "episodeTuples"},
                "delta": {
                    "reward": round(
                        float(ai_metrics["totalReward"]) - float(baseline_metrics["totalReward"]),
                        3,
                    ),
                    "objectiveCount": int(ai_metrics["objectivesMet"]) - int(baseline_metrics["objectivesMet"]),
                    "friendlyLosses": int(baseline_metrics["friendlyLosses"]) - int(ai_metrics["friendlyLosses"]),
                },
            }

            training_data = {
                "targetModule": "src/training/gpu/dataset_builder.py",
                "episodes": [
                    {"policy": "rl_agent", "tuples": ai_metrics["episodeTuples"]},
                    {"policy": "scripted_human_baseline", "tuples": baseline_metrics["episodeTuples"]},
                ],
                "engine": "phi3-medium",
            }
            return {"comparison": comparison, "trainingData": training_data, "updatedAt": _now_iso()}
        except Exception:
            return {"comparison": {}, "updatedAt": _now_iso()}
        finally:
            if env is not None:
                try:
                    env.close()
                except Exception:
                    pass

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
