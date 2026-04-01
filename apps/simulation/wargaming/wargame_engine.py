"""Session-oriented wargame engine for Layer 12."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Dict, List, Optional
from uuid import uuid4

from apps.simulation.models import WargameConfig, WargameResult, WargameSession
from apps.simulation.wargaming.llm_adversary import LLMAdversary
from apps.simulation.wargaming.turn_resolver import TurnResolver
from src.llm_core.engine_registry import TaskDomain
from src.llm_core.orchestrator import Orchestrator, QueryRequest
from src.simulation.wargame.scenario_engine import ScenarioEngine


class WargameEngine:
    """Creates sessions, resolves turns, and produces final AAR outputs."""

    def __init__(self):
        self.adversary = LLMAdversary()
        self.turn_resolver = TurnResolver()
        self.scenario_engine = ScenarioEngine()
        self._orchestrator = Orchestrator()
        self._sessions: Dict[str, WargameSession] = {}
        self._states: Dict[str, dict] = {}
        self._manual_red_orders: Dict[str, List[dict]] = {}

    def _generate_units(self, prefix: str, count: int, start_x: float, allegiance: str) -> List[dict]:
        units: List[dict] = []
        for idx in range(count):
            units.append(
                {
                    "unit_id": f"{prefix}-{idx+1}",
                    "allegiance": allegiance,
                    "type": "infantry",
                    "position": (start_x, float(idx * 10.0)),
                    "health": 1.0,
                    "size": 10,
                    "condition": 1.0,
                    "fortified": False,
                    "recon_range": 40.0,
                }
            )
        return units

    def _scenario_units(self, scenario_id: str) -> List[dict]:
        for entry in self.scenario_engine.list_scenarios():
            if entry.get("scenario_id") != scenario_id:
                continue
            scenario = self.scenario_engine.load_from_yaml(entry["path"])
            units: List[dict] = []
            for force in scenario.forces:
                for unit in force.units:
                    base = unit.get("starting_position", (0.0, 0.0, 0.0))
                    for i in range(unit.get("count", 1)):
                        units.append(
                            {
                                "unit_id": f"{force.allegiance}-{len(units)+1}",
                                "allegiance": "blue" if force.allegiance == "friendly" else "red",
                                "type": str(unit.get("type", "UNKNOWN")).lower(),
                                "position": (float(base[0]) + i * 2.0, float(base[1]) + i * 2.0),
                                "health": 1.0,
                                "size": 10,
                                "condition": 1.0,
                                "fortified": False,
                                "recon_range": 40.0,
                            }
                        )
            return units
        return []

    def create_session(self, config: WargameConfig) -> WargameSession:
        session_id = f"session-{uuid4().hex[:10]}"
        units = []
        if config.scenario_id:
            units = self._scenario_units(config.scenario_id)

        if not units:
            blue_count = int(config.parameters.get("blue_units", 8))
            red_count = int(config.parameters.get("red_units", 8))
            units.extend(self._generate_units("blue", blue_count, 0.0, "blue"))
            units.extend(self._generate_units("red", red_count, 100.0, "red"))

        session = WargameSession(
            session_id=session_id,
            config=config,
            status="setup",
            current_turn=0,
            turns=[],
            officer_id=config.parameters.get("officer_id"),
        )
        self._sessions[session_id] = session
        self._states[session_id] = {
            "turn": 0,
            "terrain": config.parameters.get("terrain", "desert"),
            "units": units,
            "initial_counts": {
                "blue": len([u for u in units if u["allegiance"] == "blue"]),
                "red": len([u for u in units if u["allegiance"] == "red"]),
            },
            "fog_of_war": {},
            "last_turn_events": [],
        }
        return session

    def start(self, session_id: str) -> bool:
        session = self._sessions.get(session_id)
        if session is None or session.status not in {"setup", "paused"}:
            return False
        session.status = "in_progress"
        if session.started_at is None:
            session.started_at = datetime.now(timezone.utc)
        return True

    def _valid_blue_orders(self, session_id: str, orders: List[dict]) -> bool:
        state = self._states.get(session_id, {})
        blue_ids = {u["unit_id"] for u in state.get("units", []) if u.get("allegiance") == "blue"}
        for order in orders:
            if str(order.get("unit_id", "")) not in blue_ids:
                return False
        return True

    def _scripted_red_orders(self, session_id: str) -> List[dict]:
        state = self._states[session_id]
        return self.adversary.decide(
            state=state,
            force_composition={
                "blue_units": [u for u in state["units"] if u["allegiance"] == "blue"],
                "red_units": [u for u in state["units"] if u["allegiance"] == "red"],
            },
            turn_number=state.get("turn", 0) + 1,
        )

    def submit_blue_orders(self, session_id: str, orders: List[dict]) -> dict:
        session = self._sessions.get(session_id)
        if session is None:
            raise ValueError("session not found")
        if session.status in {"completed", "aborted"}:
            raise ValueError("session inactive")
        if not self._valid_blue_orders(session_id, orders):
            raise ValueError("invalid blue orders")
        self.start(session_id)

        if session.config.llm_adversary:
            red_orders = self._scripted_red_orders(session_id)
        else:
            red_orders = self._manual_red_orders.pop(session_id, []) or self._scripted_red_orders(session_id)

        turn = self.turn_resolver.resolve(orders, red_orders, self._states[session_id], session.config)
        session.turns.append(turn)
        session.current_turn = turn.turn_number
        self._states[session_id] = dict(turn.state_snapshot)

        victory = None
        for event in turn.events:
            if event.get("type") == "victory":
                victory = event.get("outcome")
                break
        if victory or session.current_turn >= session.config.turn_limit:
            self.complete(session_id)

        return turn.to_dict()

    def submit_red_orders(self, session_id: str, orders: List[dict]) -> dict:
        session = self._sessions.get(session_id)
        if session is None:
            raise ValueError("session not found")
        self._manual_red_orders[session_id] = list(orders)
        return {"status": "accepted", "session_id": session_id, "orders": len(orders)}

    def get_session(self, session_id) -> Optional[WargameSession]:
        return self._sessions.get(session_id)

    def get_state(self, session_id) -> dict:
        return dict(self._states.get(session_id, {}))

    def pause(self, session_id):
        session = self._sessions.get(session_id)
        if session and session.status == "in_progress":
            session.status = "paused"

    def resume(self, session_id):
        session = self._sessions.get(session_id)
        if session and session.status == "paused":
            session.status = "in_progress"

    def abort(self, session_id):
        session = self._sessions.get(session_id)
        if session:
            session.status = "aborted"
            session.completed_at = datetime.now(timezone.utc)

    def _generate_aar(self, result: WargameResult, turns_summary: str, blue_summary: str, red_summary: str) -> str:
        prompt = (
            f"Analyze this wargame: {turns_summary}. Blue force: {blue_summary}. Red force: {red_summary}. "
            f"Outcome: {result.outcome}. Provide: 1) Executive summary 2) Key decisions and their impact "
            "3) Tactical lessons 4) Performance assessment for the Blue commander (score 0-100)."
        )
        try:
            response = self._orchestrator.process(QueryRequest(prompt=prompt, domain=TaskDomain.PLANNING))
            text = getattr(response, "text", "") or ""
            if text.strip():
                return text.strip()
        except Exception:
            pass
        return (
            "Template AAR: Blue force maintained tactical initiative in key phases. "
            "Recommendation: improve reconnaissance-to-fire synchronization and reserve timing."
        )

    def complete(self, session_id) -> WargameResult:
        session = self._sessions.get(session_id)
        if session is None:
            raise ValueError("session not found")
        if session.result is not None:
            return session.result

        total_blue_losses = sum(turn.blue_losses for turn in session.turns)
        total_red_losses = sum(turn.red_losses for turn in session.turns)
        duration = session.current_turn * session.config.turn_duration_seconds

        outcome = "incomplete"
        if session.turns:
            for event in session.turns[-1].events:
                if event.get("type") == "victory":
                    outcome = str(event.get("outcome", "incomplete"))
                    break
            if outcome == "incomplete" and session.current_turn >= session.config.turn_limit:
                outcome = "draw"

        blue_score = max(0.0, 100.0 - total_blue_losses * 1.5 + total_red_losses * 1.0)
        red_score = max(0.0, 100.0 - total_red_losses * 1.5 + total_blue_losses * 1.0)
        performance = max(0.0, min(100.0, blue_score))

        key_decisions = []
        for turn in session.turns:
            engagement_events = [e for e in turn.events if e.get("type") == "engagement"]
            if engagement_events:
                key_decisions.append(
                    {
                        "turn": turn.turn_number,
                        "engagements": len(engagement_events),
                        "impact": "high" if len(engagement_events) >= 2 else "moderate",
                    }
                )

        objectives_met = ["Maintain operational cohesion"] if outcome in {"blue_victory", "draw"} else []
        objectives_failed = [] if outcome == "blue_victory" else ["Decisive objective"]

        turns_summary = f"{len(session.turns)} turns, blue_losses={total_blue_losses}, red_losses={total_red_losses}"
        blue_summary = f"score={blue_score:.1f}, losses={total_blue_losses}"
        red_summary = f"score={red_score:.1f}, losses={total_red_losses}"

        result = WargameResult(
            wargame_id=session.config.wargame_id,
            turns_played=session.current_turn,
            duration_seconds=duration,
            outcome=outcome,
            blue_score=blue_score,
            red_score=red_score,
            blue_losses_total=total_blue_losses,
            red_losses_total=total_red_losses,
            objectives_met=objectives_met,
            objectives_failed=objectives_failed,
            key_decisions=key_decisions,
            llm_aar=None,
            lessons_learned=[
                "Preserve reconnaissance coverage before committing assault units.",
                "Use defensive fortification to absorb first contact in urban sectors.",
            ],
            performance_score=performance,
        )
        result.llm_aar = self._generate_aar(result, turns_summary, blue_summary, red_summary)

        session.result = result
        session.status = "completed"
        session.completed_at = datetime.now(timezone.utc)
        return result

    def get_sessions(self, status=None) -> List[WargameSession]:
        sessions = list(self._sessions.values())
        if status is None:
            return sessions
        return [s for s in sessions if s.status == status]

    def health_check(self) -> dict:
        return {
            "status": "operational",
            "sessions": len(self._sessions),
            "active_sessions": len([s for s in self._sessions.values() if s.status == "in_progress"]),
        }
