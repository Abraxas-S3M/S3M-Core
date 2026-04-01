"""Cyber range adapter for Phase 13 SOC training integration."""

from __future__ import annotations

from typing import Any, Dict

from services.cyber.training import CyberTrainingManager


class CyberRangeIntegrator:
    """Bridges Layer 12 training flow with Layer 07 cyber exercises."""

    def __init__(self) -> None:
        self.manager = CyberTrainingManager(auto_create_manager=False)

    def create_exercise(self, scenario_type: str = "brute_force") -> dict:
        return self.manager.create_exercise(scenario_type=scenario_type)

    def run_exercise(self, exercise: dict) -> dict:
        events = exercise.get("events", [])
        if self.manager.soc_manager is None:
            # Tactical context: offline mode still tracks drill metadata even without SOC stack loaded.
            return {
                "exercise_id": exercise.get("exercise_id", "unknown"),
                "events_processed": len(events),
                "score": 75.0,
                "mode": "simulated",
            }
        return self.manager.run_exercise(events)

    def evaluate(self, exercise_id: str) -> Dict[str, Any]:
        return self.manager.evaluate_response(exercise_id)

    def health_check(self) -> dict:
        return {
            "status": "operational",
            "exercise_types": self.manager.list_exercise_types(),
            "history_entries": len(self.manager.get_exercise_history()),
        }
