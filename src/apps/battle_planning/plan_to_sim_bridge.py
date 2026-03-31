"""Bridge OPORD outputs into simulation/autonomy mission payloads."""

from __future__ import annotations

import json
from typing import Any, Dict, List, Optional, Tuple
from uuid import uuid4

from src.apps._shared import ensure_non_empty_text, normalize_coords, safe_int
from src.llm_core.engine_registry import TaskDomain
from src.llm_core.orchestrator import Orchestrator, QueryRequest
from src.simulation.wargame.opfor_generator import OpForGenerator
from src.simulation.wargame.scenario_engine import ScenarioEngine
from src.simulation.wargame.scenario_runner import ScenarioRunner


class PlanToSimBridge:
    """Translate planning artifacts into executable simulation payloads."""

    def __init__(self) -> None:
        self._orchestrator = Orchestrator()
        self._scenario_engine = ScenarioEngine()
        self._last_scenarios: List[dict] = []

    def _extract_execution(self, opord: dict) -> str:
        execution = ((opord or {}).get("paragraphs") or {}).get("execution", {})
        if isinstance(execution, dict):
            concept = execution.get("concept", "")
            tasks = execution.get("tasks", [])
            coordinating = execution.get("coordinating", "")
            return f"concept={concept}; tasks={tasks}; coordinating={coordinating}"
        return str(execution)

    def _extract_mission(self, opord: dict) -> str:
        mission = ((opord or {}).get("paragraphs") or {}).get("mission", "")
        return str(mission)

    def _default_forces(self) -> tuple[list[dict], list[dict], list[dict], str]:
        friendly_units = [
            {"type": "FRIENDLY_UAV", "count": 4, "start_position": [50, 50, 80]},
        ]
        enemy_units = [
            {"type": "ENEMY_INFANTRY", "count": 6, "start_position": [600, 500, 0]},
            {"type": "ENEMY_UAV", "count": 2, "start_position": [800, 300, 120]},
        ]
        objectives = [
            {"description": "Complete mission objective from OPORD", "success_condition": "all_waypoints_visited"},
        ]
        return friendly_units, enemy_units, objectives, "weapons_tight"

    def _extract_json(self, text: str) -> Optional[dict]:
        raw = text.strip()
        if not raw:
            return None
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            start = raw.find("{")
            end = raw.rfind("}")
            if start >= 0 and end > start:
                try:
                    return json.loads(raw[start : end + 1])
                except json.JSONDecodeError:
                    return None
            return None

    def _parse_force_payload(self, opord: dict) -> dict:
        execution_text = self._extract_execution(opord)
        prompt = (
            "Extract from this OPORD execution paragraph the following as JSON: "
            "friendly_units (list of {type, count, start_position}), "
            "enemy_units (same), objectives (list of {description, success_condition}), "
            f"rules_of_engagement. Execution: {execution_text}"
        )
        response = self._orchestrator.process(QueryRequest(prompt=prompt, domain=TaskDomain.TACTICAL))
        parsed = self._extract_json(getattr(response, "text", "") or "")
        if not parsed:
            f_units, e_units, objs, roe = self._default_forces()
            return {
                "friendly_units": f_units,
                "enemy_units": e_units,
                "objectives": objs,
                "rules_of_engagement": roe,
                "raw_llm": getattr(response, "text", ""),
            }
        return {
            "friendly_units": parsed.get("friendly_units", []),
            "enemy_units": parsed.get("enemy_units", []),
            "objectives": parsed.get("objectives", []),
            "rules_of_engagement": parsed.get("rules_of_engagement", "weapons_tight"),
            "raw_llm": getattr(response, "text", ""),
        }

    def _units_to_force(self, units: list[dict], name: str, allegiance: str) -> dict:
        normalized = []
        for unit in units:
            utype = str(unit.get("type", "UNKNOWN")).upper()
            count = max(1, safe_int(unit.get("count", 1), 1))
            pos = normalize_coords(unit.get("start_position", unit.get("position", [0, 0, 0])), dims=3)
            normalized.append({"type": utype, "count": count, "position": list(pos), "behavior": "patrol"})
        if not normalized:
            normalized = [{"type": "UNKNOWN", "count": 1, "position": [0, 0, 0], "behavior": "hold"}]
        return {"name": name, "allegiance": allegiance, "units": normalized}

    def opord_to_scenario(self, opord: dict, terrain_bounds: tuple = None) -> dict:
        """Convert OPORD dictionary to ScenarioEngine.load_from_dict-compatible payload."""
        if not isinstance(opord, dict):
            raise ValueError("opord must be a dictionary")
        payload = self._parse_force_payload(opord)
        mission = self._extract_mission(opord)
        objectives = payload.get("objectives") or [
            {"description": mission or "Execute mission", "success_condition": "all_waypoints_visited"}
        ]
        terrain = {
            "bounds": list(terrain_bounds) if terrain_bounds else [[0, 0, 0], [1000, 1000, 200]],
            "type": "mixed",
            "obstacles": [],
        }
        scenario = {
            "scenario": {
                "scenario_id": f"phase11-{uuid4().hex[:10]}",
                "name": "Phase11 OPORD Scenario",
                "description": f"Scenario synthesized from OPORD: {mission[:120]}",
                "type": "custom",
                "terrain": terrain,
                "weather": {"visibility": 0.9, "wind_speed": 5.0, "wind_direction": 180, "precipitation": "none"},
                "forces": [
                    self._units_to_force(payload.get("friendly_units", []), "Blue Force", "friendly"),
                    self._units_to_force(payload.get("enemy_units", []), "Red Force", "enemy"),
                ],
                "objectives": objectives,
                "rules_of_engagement": str(payload.get("rules_of_engagement", "weapons_tight")),
                "duration_seconds": safe_int(((opord.get("context") or {}).get("duration_seconds", 600)), 600),
                "parameters": {"source": "opord_to_scenario"},
            }
        }
        self._last_scenarios.append(scenario)
        self._last_scenarios = self._last_scenarios[-25:]
        return scenario

    def run_scenario(self, scenario: dict) -> dict:
        """Run scenario payload and return AAR dictionary."""
        if not isinstance(scenario, dict):
            raise ValueError("scenario must be a dictionary")
        scenario_def = self._scenario_engine.load_from_dict(scenario)
        runner = ScenarioRunner()
        runner.load(scenario_def)
        opfor = OpForGenerator(strategy="adaptive")
        aar = runner.run(max_ticks=1200, tick_dt=0.1, opfor_controller=opfor)
        return aar.to_dict()

    def opord_to_mission(self, opord: dict) -> dict:
        """Convert OPORD into autonomy-mission-like dictionary payload."""
        if not isinstance(opord, dict):
            raise ValueError("opord must be a dictionary")
        mission_text = self._extract_mission(opord)
        execution = ((opord.get("paragraphs") or {}).get("execution") or {})
        tasks = execution.get("tasks", []) if isinstance(execution, dict) else []
        waypoints: List[Tuple[float, float, float]] = []
        for idx, task in enumerate(tasks):
            _ = task
            waypoints.append((150.0 + idx * 100.0, 150.0 + idx * 80.0, 80.0))
        if not waypoints:
            waypoints = [(200.0, 200.0, 80.0), (400.0, 500.0, 80.0)]
        mission_type = "PATROL"
        lowered = mission_text.lower()
        if "recon" in lowered:
            mission_type = "RECON"
        elif "intercept" in lowered or "engage" in lowered:
            mission_type = "INTERCEPT"
        signal_text = str(
            (((opord.get("paragraphs") or {}).get("command_signal") or {}).get("signal", "weapons_tight"))
        )
        return {
            "mission_id": f"mission-{uuid4().hex[:10]}",
            "mission_type": mission_type,
            "waypoints": [tuple(wp) for wp in waypoints],
            "rules_of_engagement": signal_text if signal_text.strip() else "weapons_tight",
            "source_opord_id": opord.get("opord_id"),
        }

