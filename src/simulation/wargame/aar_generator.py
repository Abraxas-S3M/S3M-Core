"""After Action Review generator for tactical simulation runs."""

from __future__ import annotations

from datetime import datetime, timezone
from statistics import mean
from typing import Any, Dict, List, Optional
from uuid import uuid4

from src.llm_core import Orchestrator, QueryRequest, TaskDomain
from src.simulation.models import AARReport, ReplayArtifact, ScenarioDefinition, SimulationState


class AARGenerator:
    """Generate military exercise AARs with optional LLM narrative analysis."""

    def __init__(self) -> None:
        self._orchestrator: Optional[Orchestrator] = None

    def _friendly_losses(self, scenario: ScenarioDefinition, final_state: SimulationState) -> int:
        initial = sum(
            unit["count"]
            for force in scenario.forces
            if force.allegiance == "friendly"
            for unit in force.units
        )
        remaining = len(final_state.friendly_entities())
        return max(0, initial - remaining)

    def _enemy_losses(self, scenario: ScenarioDefinition, final_state: SimulationState) -> int:
        initial = sum(
            unit["count"]
            for force in scenario.forces
            if force.allegiance == "enemy"
            for unit in force.units
        )
        remaining = len(final_state.enemy_entities())
        return max(0, initial - remaining)

    def _distance_traveled(self, timeline: List[Dict[str, Any]]) -> float:
        distance = 0.0
        for event in timeline:
            event_type = str(event.get("event", event.get("type", "")))
            if event_type != "movement":
                continue
            distance += float(event.get("distance", 0.0))
        return distance

    def _objective_met(
        self,
        objective: Dict[str, Any],
        scenario: ScenarioDefinition,
        final_state: SimulationState,
        friendly_losses: int,
        enemy_losses: int,
    ) -> bool:
        if "met" in objective:
            return bool(objective.get("met"))
        condition = str(objective.get("success_condition", "")).strip()
        if not condition:
            return False
        env = {
            "friendly_losses": friendly_losses,
            "enemy_losses": enemy_losses,
            "enemies_detected": int(final_state.metadata.get("enemies_detected", len(final_state.enemy_entities()))),
            "all_waypoints_visited": bool(final_state.metadata.get("all_waypoints_visited", False)),
            "convoy_arrived": bool(final_state.metadata.get("convoy_arrived", False)),
            "installation_intact": bool(final_state.metadata.get("installation_intact", True)),
        }
        try:
            return bool(eval(condition, {"__builtins__": {}}, env))
        except Exception:
            return False

    def _query_llm(self, prompt: str) -> Optional[str]:
        try:
            if self._orchestrator is None:
                self._orchestrator = Orchestrator()
            request = QueryRequest(prompt=prompt, domain=TaskDomain.PLANNING, require_consensus=False)
            response = self._orchestrator.process(request)
            text = getattr(response, "text", None)
            if isinstance(text, str) and text.strip():
                return text.strip()
        except Exception:
            return None
        return None

    def _extract_lessons(self, llm_analysis: Optional[str], statistics: Dict[str, Any]) -> List[str]:
        if llm_analysis:
            lessons: List[str] = []
            for line in llm_analysis.splitlines():
                stripped = line.strip("-* \t")
                if len(stripped) > 20 and len(lessons) < 6:
                    lessons.append(stripped)
            if lessons:
                return lessons
        generated = [
            "Maintain standoff distance before committing friendly units to dense threat zones.",
            "Prioritize synchronized detection-to-engagement loops to reduce reaction latency.",
        ]
        if int(statistics.get("friendly_losses", 0)) > int(statistics.get("enemy_losses", 0)):
            generated.append("Improve force protection and route discipline under high-contact conditions.")
        else:
            generated.append("Current tactics achieved favorable exchange; preserve command-and-control tempo.")
        return generated

    def generate(
        self,
        scenario: ScenarioDefinition,
        final_state: SimulationState,
        timeline: List[Dict[str, Any]],
        replay: Optional[ReplayArtifact] = None,
    ) -> AARReport:
        """Generate complete AAR with statistics and optional narrative analysis."""
        friendly_losses = self._friendly_losses(scenario, final_state)
        enemy_losses = self._enemy_losses(scenario, final_state)
        duration = float(final_state.sim_time_seconds)
        objectives_met: List[str] = []
        objectives_failed: List[str] = []
        primary_objectives = [obj for obj in scenario.objectives if int(obj.get("priority", 1)) == 1] or list(scenario.objectives)
        for objective in scenario.objectives:
            description = str(objective.get("description", "")).strip() or "Unnamed objective"
            if self._objective_met(objective, scenario, final_state, friendly_losses, enemy_losses):
                objectives_met.append(description)
            else:
                objectives_failed.append(description)

        event_types = [str(e.get("event", e.get("type", ""))) for e in timeline]
        engagements = len([event for event in event_types if event == "engagement_started"])
        killed = len([event for event in event_types if event == "entity_killed"])

        if len(final_state.friendly_entities()) == 0:
            outcome = "defeat"
        elif primary_objectives and all(
            self._objective_met(obj, scenario, final_state, friendly_losses, enemy_losses) for obj in primary_objectives
        ):
            outcome = "victory"
        elif friendly_losses == 0 and enemy_losses == 0:
            outcome = "incomplete"
        else:
            outcome = "draw"

        statistics: Dict[str, Any] = {
            "engagement_count": engagements,
            "shots_fired": engagements * 5,
            "distance_traveled": round(self._distance_traveled(timeline), 2),
            "friendly_losses": friendly_losses,
            "enemy_losses": enemy_losses,
            "duration_seconds": duration,
            "killed_events": killed,
            "entities_remaining": len(final_state.entities),
        }
        if replay is not None:
            statistics["replay_id"] = replay.replay_id

        prompt = (
            "Analyze this military exercise and provide: 1) Executive summary "
            "2) Key decisions and their impact 3) Tactical lessons learned "
            "4) Recommendations for improvement. Format as a military After Action Review.\n\n"
            f"Scenario: {scenario.name} ({scenario.scenario_type})\n"
            f"Outcome: {outcome}\n"
            f"Statistics: {statistics}\n"
            f"Timeline events: {timeline[:20]}"
        )
        llm_analysis = self._query_llm(prompt)
        lessons = self._extract_lessons(llm_analysis, statistics)

        return AARReport(
            aar_id=str(uuid4()),
            scenario_id=scenario.scenario_id,
            timestamp=datetime.now(timezone.utc),
            duration_seconds=duration,
            outcome=outcome,
            friendly_losses=friendly_losses,
            enemy_losses=enemy_losses,
            objectives_met=objectives_met,
            objectives_failed=objectives_failed,
            timeline=timeline,
            llm_analysis=llm_analysis,
            lessons_learned=lessons,
            statistics=statistics,
        )

    def generate_comparison(self, aars: List[AARReport]) -> Dict[str, Any]:
        """Compare multiple AAR runs for tactic selection and force tuning."""
        if not aars:
            return {"total_runs": 0, "win_rate": 0.0, "best_run": None}
        victories = [aar for aar in aars if aar.outcome == "victory"]
        best = sorted(
            aars,
            key=lambda aar: (-int(aar.enemy_losses), int(aar.friendly_losses), float(aar.duration_seconds)),
        )[0]
        return {
            "total_runs": len(aars),
            "win_rate": round(len(victories) / len(aars), 3),
            "avg_friendly_losses": round(mean(aar.friendly_losses for aar in aars), 3),
            "avg_enemy_losses": round(mean(aar.enemy_losses for aar in aars), 3),
            "best_run": best.to_dict(),
        }
