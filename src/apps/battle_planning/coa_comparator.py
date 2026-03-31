"""Compare battle planning Courses of Action (COAs)."""

from __future__ import annotations

from copy import deepcopy
from typing import Any, Dict, List

from src.apps._shared import ensure_non_empty_text, utc_now_iso
from src.apps.battle_planning.ops_order_generator import OpsOrderGenerator
from src.apps.battle_planning.plan_to_sim_bridge import PlanToSimBridge
from src.llm_core.engine_registry import TaskDomain
from src.llm_core.orchestrator import Orchestrator, QueryRequest


class COAComparator:
    """Generate, simulate, and compare COA variants for one mission."""

    def __init__(self) -> None:
        self.ops_generator = OpsOrderGenerator()
        self.bridge = PlanToSimBridge()
        self.orchestrator = Orchestrator()

    def _tactic_profiles(self) -> List[dict]:
        return [
            {
                "coa_id": 1,
                "name": "Aggressive",
                "approach": "aggressive",
                "roe": "weapons_free",
                "formation": "line_abreast",
                "offset": (0.0, 0.0, 0.0),
            },
            {
                "coa_id": 2,
                "name": "Cautious",
                "approach": "cautious",
                "roe": "weapons_tight",
                "formation": "wedge",
                "offset": (-60.0, 80.0, 0.0),
            },
            {
                "coa_id": 3,
                "name": "Stealth",
                "approach": "stealth",
                "roe": "weapons_hold",
                "formation": "column",
                "offset": (-120.0, 130.0, 0.0),
            },
        ]

    def _apply_profile(self, scenario: dict, profile: dict) -> dict:
        variant = deepcopy(scenario)
        variant["rules_of_engagement"] = profile["roe"]
        params = variant.setdefault("parameters", {})
        params["friendly_approach"] = profile["approach"]
        params["formation"] = profile["formation"]
        dx, dy, dz = profile["offset"]
        for force in variant.get("forces", []):
            if force.get("allegiance") != "friendly":
                continue
            for unit in force.get("units", []):
                pos = unit.get("position", unit.get("starting_position", (0, 0, 0)))
                if isinstance(pos, list):
                    pos = tuple(pos)
                if isinstance(pos, tuple) and len(pos) >= 3:
                    unit["position"] = [float(pos[0]) + dx, float(pos[1]) + dy, float(pos[2]) + dz]
                unit["behavior"] = profile["approach"]
        return variant

    def _summarize_aar(self, aar: dict) -> str:
        return (
            f"Outcome={aar.get('outcome', 'unknown')}, "
            f"friendly_losses={aar.get('friendly_losses', 0)}, "
            f"enemy_losses={aar.get('enemy_losses', 0)}, "
            f"objectives_met={len(aar.get('objectives_met', []))}, "
            f"duration={aar.get('duration_seconds', 0):.1f}s"
        )

    def _score(self, aar: dict) -> float:
        objectives = len(aar.get("objectives_met", []))
        friendly_losses = float(aar.get("friendly_losses", 0))
        duration = float(aar.get("duration_seconds", 0))
        outcome_bonus = 1.0 if str(aar.get("outcome", "")).lower() == "victory" else 0.0
        return objectives * 3.0 + outcome_bonus * 2.0 - friendly_losses * 2.0 - duration / 600.0

    def _llm_recommendation(self, mission_brief: str, summaries: list[str]) -> tuple[str, str]:
        prompt = (
            f"Compare these 3 courses of action for the mission '{mission_brief}'. "
            f"COA 1: {summaries[0]}. COA 2: {summaries[1]}. COA 3: {summaries[2]}. "
            "Recommend the best COA and explain why."
        )
        try:
            response = self.orchestrator.process(QueryRequest(prompt=prompt, domain=TaskDomain.REASONING))
            analysis = getattr(response, "text", "") or ""
            if "pending" in analysis.lower() or "not yet loaded" in analysis.lower():
                raise RuntimeError("Reasoning LLM unavailable")
            return analysis.strip(), analysis.strip()
        except Exception:
            return "", "LLM analysis unavailable — metrics-only recommendation"

    def compare(self, mission_brief: str, num_coas: int = 3) -> dict:
        """Compare up to 3 doctrinal COA variants for mission."""
        mission_brief = ensure_non_empty_text(mission_brief, "mission_brief")
        if not isinstance(num_coas, int) or num_coas <= 0:
            raise ValueError("num_coas must be a positive integer")
        num_coas = min(num_coas, 3)

        opord = self.ops_generator.generate(mission_brief)
        base_scenario = self.bridge.opord_to_scenario(opord)
        profiles = self._tactic_profiles()[:num_coas]

        coas: List[dict] = []
        scores: dict[int, float] = {}
        for profile in profiles:
            scenario = self._apply_profile(base_scenario, profile)
            aar = self.bridge.run_scenario(scenario)
            summary = self._summarize_aar(aar)
            score = self._score(aar)
            scores[profile["coa_id"]] = score
            coas.append(
                {
                    "coa_id": profile["coa_id"],
                    "name": profile["name"],
                    "aar": aar,
                    "summary": summary,
                }
            )

        ranking = [coa_id for coa_id, _ in sorted(scores.items(), key=lambda kv: kv[1], reverse=True)]
        metrics = {
            "scores": scores,
            "best_coa": ranking[0] if ranking else None,
            "timestamp": utc_now_iso(),
        }

        summaries = [coa["summary"] for coa in coas]
        recommendation, llm_analysis = self._llm_recommendation(mission_brief, summaries + ["", "", ""][: max(0, 3 - len(summaries))])
        if not recommendation:
            best = ranking[0] if ranking else 1
            recommendation = (
                f"Metrics-only recommendation: select COA {best} "
                f"based on objective completion and minimized friendly losses."
            )

        return {
            "mission_brief": mission_brief,
            "coas": coas,
            "comparison": {"metrics": metrics, "ranking": ranking},
            "recommendation": recommendation,
            "llm_analysis": llm_analysis,
        }
