"""High-level wargaming orchestrator for Layer 12 workflows."""

from __future__ import annotations

from collections import Counter
from statistics import mean
from typing import Dict, List
from uuid import uuid4

from apps.simulation.models import WargameConfig, WargameResult, WargameSession
from apps.simulation.wargaming.wargame_engine import WargameEngine
from src.apps.battle_planning.battle_planner import BattlePlanner


class WargameSuite:
    """Facade for rapid wargames, COA runs, and officer analytics."""

    def __init__(self):
        self.engine = WargameEngine()

    def _auto_blue_orders(self, state: dict) -> List[dict]:
        blue = [u for u in state.get("units", []) if u.get("allegiance") == "blue"]
        red = [u for u in state.get("units", []) if u.get("allegiance") == "red"]
        orders: List[dict] = []
        for unit in blue:
            if not red:
                orders.append({"unit_id": unit["unit_id"], "action": "defend", "target": tuple(unit.get("position", (0.0, 0.0)))})
                continue
            ux, uy = unit.get("position", (0.0, 0.0))
            target = min(red, key=lambda r: (r.get("position", (0.0, 0.0))[0] - ux) ** 2 + (r.get("position", (0.0, 0.0))[1] - uy) ** 2)
            orders.append(
                {
                    "unit_id": unit["unit_id"],
                    "action": "attack",
                    "target": tuple(target.get("position", (0.0, 0.0))),
                    "target_unit_id": target.get("unit_id"),
                    "reasoning": "Auto blue-force engagement order.",
                }
            )
        return orders

    def quick_wargame(self, name: str, blue_units: int, red_units: int, turns: int = 20, adversary: str = "competent") -> WargameResult:
        config = WargameConfig(
            wargame_id=f"wg-{uuid4().hex[:10]}",
            name=name,
            description="Quick tactical training wargame",
            wargame_type="tactical",
            scenario_id=None,
            blue_force_id="quick-blue",
            red_force_id="quick-red",
            turn_limit=turns,
            turn_duration_seconds=60.0,
            llm_adversary=True,
            adversary_difficulty=adversary,
            rules_of_engagement="weapons_tight",
            victory_conditions=[{"type": "eliminate", "target": "red", "threshold_pct": 75}],
            parameters={"blue_units": int(blue_units), "red_units": int(red_units), "terrain": "desert"},
        )
        session = self.engine.create_session(config)
        self.engine.start(session.session_id)
        for _ in range(turns):
            if self.engine.get_session(session.session_id).status == "completed":
                break
            state = self.engine.get_state(session.session_id)
            orders = self._auto_blue_orders(state)
            self.engine.submit_blue_orders(session.session_id, orders)
        return self.engine.complete(session.session_id)

    def create_coa_wargame(self, mission_brief: str, num_coas: int = 3) -> List[WargameResult]:
        planner = BattlePlanner()
        opord = planner.ops_generator.generate(mission_brief)
        results: List[WargameResult] = []
        for idx in range(max(1, num_coas)):
            results.append(
                self.quick_wargame(
                    name=f"COA {idx+1} - {opord.get('title', 'Mission')}",
                    blue_units=8 + idx,
                    red_units=9 + idx,
                    turns=12,
                    adversary=["competent", "expert", "grandmaster"][idx % 3],
                )
            )
        return results

    def create_from_orbat(self, blue_force_id: str, red_force_id: str, terrain: str = "desert") -> WargameSession:
        config = WargameConfig(
            wargame_id=f"wg-{uuid4().hex[:10]}",
            name=f"ORBAT Wargame {blue_force_id} vs {red_force_id}",
            description="ORBAT-originated tactical simulation",
            wargame_type="operational",
            scenario_id=None,
            blue_force_id=blue_force_id,
            red_force_id=red_force_id,
            turn_limit=30,
            turn_duration_seconds=60.0,
            llm_adversary=True,
            adversary_difficulty="competent",
            rules_of_engagement="weapons_tight",
            victory_conditions=[{"type": "eliminate", "target": "red", "threshold_pct": 70}],
            parameters={"terrain": terrain, "blue_units": 10, "red_units": 10},
        )
        return self.engine.create_session(config)

    def get_leaderboard(self, limit: int = 20) -> List[dict]:
        scores: Dict[str, List[float]] = {}
        for session in self.engine.get_sessions(status="completed"):
            if session.officer_id and session.result:
                scores.setdefault(session.officer_id, []).append(session.result.performance_score)
        rows = [
            {"officer_id": officer, "average_score": round(mean(vals), 2), "sessions": len(vals)}
            for officer, vals in scores.items()
        ]
        rows.sort(key=lambda r: r["average_score"], reverse=True)
        return rows[: max(1, limit)]

    def get_statistics(self) -> dict:
        sessions = self.engine.get_sessions()
        completed = [s for s in sessions if s.result]
        outcomes = Counter([s.result.outcome for s in completed])
        avg_duration = mean([s.result.duration_seconds for s in completed]) if completed else 0.0
        by_type = Counter([s.config.wargame_type for s in sessions])
        return {
            "total_sessions": len(sessions),
            "by_type": dict(by_type),
            "avg_duration": round(avg_duration, 2),
            "outcome_distribution": dict(outcomes),
        }
