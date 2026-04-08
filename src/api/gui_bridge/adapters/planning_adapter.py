"""Planning workspace adapter.

Reshapes battle planning data into mission phases and COAs.

Internal dependencies:
- src.apps.battle_planning (plans, COA comparison)
- src.replanning.plan_repair_engine (optional)
"""

from datetime import datetime, timezone

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
        try:
            from src.replanning.plan_repair_engine import PlanRepairEngine

            engine = PlanRepairEngine()
            triggers = engine.get_active_triggers() if hasattr(engine, "get_active_triggers") else []
            return {"triggers": triggers, "updatedAt": _now_iso()}
        except Exception:
            return {"triggers": [], "updatedAt": _now_iso()}

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
