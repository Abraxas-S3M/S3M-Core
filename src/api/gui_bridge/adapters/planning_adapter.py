"""Planning workspace adapter.

Reshapes battle planning data into mission phases and COAs.

Internal dependencies:
- src.apps.battle_planning (plans, COA comparison)
- src.replanning.plan_repair_engine (optional)
"""

from datetime import datetime, timezone
from typing import Any

from src.api.gui_bridge.models.gui_schemas import (
    GUICOA,
    GUICOAData,
    GUIMissionPhase,
    GUIPlanningPhasesData,
)
from src.api.gui_bridge.training_emitter import emit_training_record


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class PlanningAdapter:
    def get_phases(self) -> dict:
        phases = self._build_phases()
        result = GUIPlanningPhasesData(phases=phases, updatedAt=_now_iso()).model_dump()
        emit_training_record("planning", {"query": "phases"}, result)
        return result

    def get_coas(self) -> dict:
        coas = self._build_coas()
        result = GUICOAData(coursesOfAction=coas, updatedAt=_now_iso()).model_dump()
        emit_training_record("planning", {"query": "coas"}, result)
        return result

    def _build_phases(self):
        try:
            from src.apps.battle_planning import planner

            if hasattr(planner, "get_plans"):
                plans = planner.get_plans()
                # Map plans to phases — each plan's phases become mission phases
                phases = []
                for p in (plans if isinstance(plans, list) else []):
                    pd = p if isinstance(p, dict) else {}
                    for i, phase in enumerate(pd.get("phases", [])):
                        phases.append(
                            GUIMissionPhase(
                                id=f"{pd.get('id', 'P')}-PH{i + 1}",
                                name=phase.get("name", f"Phase {i + 1}"),
                                status=phase.get("status", "planned"),
                                startTime=phase.get("start"),
                                endTime=phase.get("end"),
                                objectives=phase.get("objectives", []),
                            )
                        )
                if phases:
                    return phases
        except Exception:
            pass
        return self._default_phases()

    def _build_coas(self):
        try:
            from src.apps.battle_planning.battle_planner import BattlePlanner

            bp = BattlePlanner()
            result = bp.plan_with_comparison("Current operational mission", num_coas=3)
            comparison = result.get("comparison", {})
            coa_results = comparison.get("coa_results", [])
            if coa_results:
                gui_coas = []
                for cr in coa_results:
                    aar = cr.get("aar", {})
                    profile = cr.get("profile", {})
                    # Tactical context: convert simulated friendly losses into
                    # a bounded operator-facing mission risk score.
                    gui_coas.append(
                        GUICOA(
                            id=f"COA-{profile.get('coa_id', 0)}",
                            name=profile.get("name", "Unknown"),
                            description=profile.get("approach", ""),
                            riskScore=min(100, max(0, int(aar.get("friendly_losses", 0) * 20))),
                            successProbability=1.0 if aar.get("outcome") == "victory" else 0.5,
                            selected=(cr == coa_results[0]),  # top-ranked
                            strengths=profile.get("strengths", []),
                            weaknesses=profile.get("weaknesses", []),
                        )
                    )
                return gui_coas
        except Exception:
            pass
        return self._default_coas()

    def get_replan_triggers(self) -> dict:
        triggers = []
        try:
            from src.replanning.plan_repair_engine import PlanRepairEngine

            engine = PlanRepairEngine()
            triggers = engine.get_active_triggers() if hasattr(engine, "get_active_triggers") else []
        except Exception:
            triggers = []

        return {
            "triggers": triggers,
            "replanOptions": self._build_replan_options(triggers),
            "updatedAt": _now_iso(),
        }

    def _build_replan_options(self, triggers: list[Any]) -> list[dict]:
        try:
            from src.planning.route_graph import TacticalRouteGraph
        except Exception:
            return []

        grid_size = self._extract_grid_size(triggers)
        start = self._extract_waypoint(triggers, key="start", default=(0, 0))
        end = self._extract_waypoint(triggers, key="end", default=(grid_size[0] - 1, grid_size[1] - 1))
        obstacles = self._extract_collection(triggers, singular_key="obstacle", plural_key="obstacles")
        threats = self._extract_collection(triggers, singular_key="threat", plural_key="threats")

        try:
            route_graph = TacticalRouteGraph().build_from_terrain(grid_size=grid_size, obstacles=obstacles)
            route_graph.add_threat_overlay(threats)
            alternate_routes = route_graph.find_alternate_routes(start=start, end=end, k=3)
        except Exception:
            return []

        options = []
        for index, route in enumerate(alternate_routes, start=1):
            # Tactical context: each option represents a distinct maneuver
            # corridor that operators can select during rapid replanning.
            options.append(
                {
                    "optionId": f"ALT-{index}",
                    "waypoints": [{"x": waypoint[0], "y": waypoint[1]} for waypoint in route],
                }
            )
        return options

    @staticmethod
    def _extract_grid_size(triggers: list[Any]) -> tuple[int, int]:
        default_size = (12, 12)
        for trigger in triggers:
            if not isinstance(trigger, dict):
                continue
            grid_size = trigger.get("grid_size")
            if isinstance(grid_size, (list, tuple)) and len(grid_size) == 2:
                try:
                    width = max(2, int(grid_size[0]))
                    height = max(2, int(grid_size[1]))
                    return width, height
                except (TypeError, ValueError):
                    continue
        return default_size

    @staticmethod
    def _extract_waypoint(triggers: list[Any], *, key: str, default: tuple[int, int]) -> tuple[int, int]:
        for trigger in triggers:
            if not isinstance(trigger, dict):
                continue
            candidate = trigger.get(key)
            if isinstance(candidate, dict) and "x" in candidate and "y" in candidate:
                try:
                    return int(candidate["x"]), int(candidate["y"])
                except (TypeError, ValueError):
                    continue
            if isinstance(candidate, (list, tuple)) and len(candidate) >= 2:
                try:
                    return int(candidate[0]), int(candidate[1])
                except (TypeError, ValueError):
                    continue
        return default

    @staticmethod
    def _extract_collection(
        triggers: list[Any], *, singular_key: str, plural_key: str
    ) -> list[dict | tuple[int, int]]:
        entries: list[dict | tuple[int, int]] = []
        for trigger in triggers:
            if not isinstance(trigger, dict):
                continue

            singular = trigger.get(singular_key)
            if singular is not None:
                entries.append(singular)

            plural = trigger.get(plural_key)
            if isinstance(plural, list):
                entries.extend(plural)
            elif plural is not None:
                entries.append(plural)
        return entries

    def get_suggestions(self, plan_context: str = "") -> dict:
        try:
            from src.llm_core.orchestrator import Orchestrator, QueryRequest
            from src.llm_core.engine_registry import TaskDomain

            orch = Orchestrator()
            prompt = f"Given current plan context: {plan_context}. Suggest 3 plan modifications."
            try:
                request = QueryRequest(prompt=prompt, domain=TaskDomain.PLANNING, max_tokens=512)
            except TypeError:
                request = QueryRequest(prompt=prompt, domain=TaskDomain.PLANNING)

            result = orch.query(request) if hasattr(orch, "query") else orch.process(request)
            text = result.get("text", "") if isinstance(result, dict) else getattr(result, "text", "")
            return {"suggestions": text, "engine": "mixtral", "updatedAt": _now_iso()}
        except Exception:
            return {"suggestions": "LLM unavailable", "updatedAt": _now_iso()}

    @staticmethod
    def _default_phases():
        return [
            GUIMissionPhase(
                id="PH-1",
                name="Shape",
                status="complete",
                objectives=["ISR collection", "Cyber recon"],
            ),
            GUIMissionPhase(
                id="PH-2",
                name="Deter",
                status="active",
                objectives=["Forward positioning", "Show of force"],
            ),
            GUIMissionPhase(
                id="PH-3",
                name="Seize Initiative",
                status="planned",
                objectives=["Secure crossing points"],
            ),
            GUIMissionPhase(
                id="PH-4",
                name="Dominate",
                status="planned",
                objectives=["Defeat enemy main body"],
            ),
            GUIMissionPhase(
                id="PH-5",
                name="Stabilize",
                status="planned",
                objectives=["Establish security"],
            ),
        ]

    @staticmethod
    def _default_coas():
        return [
            GUICOA(
                id="COA-1",
                name="Frontal Assault",
                description="Direct approach through primary axis",
                riskScore=78,
                successProbability=0.55,
                selected=False,
                strengths=["Speed", "Simplicity"],
                weaknesses=["High casualties", "Predictable"],
            ),
            GUICOA(
                id="COA-2",
                name="Envelopment",
                description="Flanking maneuver via secondary route",
                riskScore=52,
                successProbability=0.72,
                selected=True,
                strengths=["Surprise", "Lower risk"],
                weaknesses=["Complex coordination", "Longer timeline"],
            ),
            GUICOA(
                id="COA-3",
                name="Infiltration",
                description="Covert penetration with SOF elements",
                riskScore=65,
                successProbability=0.63,
                selected=False,
                strengths=["Minimal footprint", "Deniability"],
                weaknesses=["Limited combat power", "Comms risk"],
            ),
        ]
