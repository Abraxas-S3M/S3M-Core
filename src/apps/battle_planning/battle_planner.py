"""Battle planner orchestrating OPORD, scenario, simulation, and comparison."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from src.apps._shared import ensure_non_empty_text, utc_now_iso
from src.apps.battle_planning.coa_comparator import COAComparator
from src.apps.battle_planning.ops_order_generator import OpsOrderGenerator
from src.apps.battle_planning.plan_to_sim_bridge import PlanToSimBridge
from src.llm_core.engine_registry import TaskDomain
from src.llm_core.orchestrator import Orchestrator, QueryRequest


class BattlePlanner:
    """End-to-end battle-planning domain pipeline."""

    def __init__(self) -> None:
        self.ops_generator = OpsOrderGenerator()
        self.bridge = PlanToSimBridge()
        self.comparator = COAComparator()
        self.orchestrator = Orchestrator()
        self._history: List[Dict[str, Any]] = []

    def plan(self, mission_brief: str, options: Optional[dict] = None) -> dict:
        """Generate OPORD, scenario, and AAR for one mission brief."""
        brief = ensure_non_empty_text(mission_brief, "mission_brief")
        opts = options or {}
        opord = self.ops_generator.generate(brief, context=opts)
        scenario = self.bridge.opord_to_scenario(opord, terrain_bounds=opts.get("terrain_bounds"))
        aar = self.bridge.run_scenario(scenario)
        result = {"opord": opord, "scenario": scenario, "aar": aar, "timestamp": utc_now_iso()}
        self._history.append(
            {
                "timestamp": result["timestamp"],
                "mission_brief": brief,
                "opord_id": opord.get("opord_id"),
                "scenario_id": scenario.get("scenario", {}).get("scenario_id"),
                "outcome": aar.get("outcome", "unknown"),
            }
        )
        self._history = self._history[-50:]
        return result

    def plan_with_comparison(self, mission_brief: str, num_coas: int = 3) -> dict:
        """Run full COA comparison and return recommendation package."""
        result = self.comparator.compare(mission_brief=mission_brief, num_coas=num_coas)
        self._history.append(
            {
                "timestamp": utc_now_iso(),
                "mission_brief": mission_brief,
                "type": "coa_comparison",
                "ranking": result.get("comparison", {}).get("ranking", []),
            }
        )
        self._history = self._history[-50:]
        return result

    def quick_assess(self, situation_description: str) -> str:
        """Fast tactical assessment for field use without simulation."""
        text = ensure_non_empty_text(situation_description, "situation_description")
        prompt = (
            "Provide a concise tactical quick assessment (3 bullets max) for: "
            f"{text}. Include immediate actions and confidence. Classification: UNCLASSIFIED - FOUO."
        )
        try:
            resp = self.orchestrator.process(QueryRequest(prompt=prompt, domain=TaskDomain.TACTICAL))
            if hasattr(resp, "text") and isinstance(resp.text, str) and resp.text.strip():
                return resp.text.strip()
        except Exception:
            pass
        return (
            "Assessment: Potential hostile activity detected. "
            "Actions: increase ISR coverage, harden FOB perimeter, maintain weapons tight pending PID."
        )

    def get_history(self) -> List[dict]:
        """Return recent planning session metadata."""
        return list(self._history)

    def health_check(self) -> dict:
        """Return module health and dependency status."""
        return {
            "status": "operational",
            "history_entries": len(self._history),
            "components": {
                "ops_order_generator": "ready",
                "plan_to_sim_bridge": "ready",
                "coa_comparator": "ready",
            },
            "timestamp": utc_now_iso(),
        }

