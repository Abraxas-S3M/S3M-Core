"""Top-level manager for Layer 12 training and simulation workflows."""

from __future__ import annotations

from typing import List

from apps.simulation.battle_visualizer import BattleVisualizer
from apps.simulation.cyber_range import CyberRangeIntegrator
from apps.simulation.exercises import ExerciseFramework
from apps.simulation.models import Exercise, ExerciseScore, WargameConfig, WargameResult, WargameSession
from apps.simulation.scenario_author import ScenarioAuthor
from apps.simulation.training import TrainingPortal
from apps.simulation.wargaming import WargameSuite


class TrainingSimManager:
    """Unified facade for wargaming, exercises, scenarios, and officer training."""

    def __init__(self):
        self.wargame_suite = WargameSuite()
        self.exercise_framework = ExerciseFramework()
        self.training_portal = TrainingPortal()
        self.scenario_author = ScenarioAuthor()
        self.battle_visualizer = BattleVisualizer()
        self.cyber_range = CyberRangeIntegrator()

    def run_quick_wargame(self, name, blue_units, red_units, turns, adversary) -> WargameResult:
        return self.wargame_suite.quick_wargame(name, blue_units, red_units, turns=turns, adversary=adversary)

    def create_wargame(self, config: WargameConfig) -> WargameSession:
        session = self.wargame_suite.engine.create_session(config)
        self.battle_visualizer.register_session(session)
        return session

    def submit_orders(self, session_id, orders) -> dict:
        turn = self.wargame_suite.engine.submit_blue_orders(session_id, orders)
        session = self.wargame_suite.engine.get_session(session_id)
        if session:
            self.battle_visualizer.register_session(session)
        return turn

    def create_exercise(self, name, type, phases, participants) -> Exercise:
        return self.exercise_framework.create_exercise(
            name=name,
            exercise_type=type,
            description=name,
            phases=phases,
            participants=participants,
        )

    def create_tabletop(self, name, brief, participants) -> Exercise:
        return self.exercise_framework.create_tabletop(name=name, scenario_brief=brief, participants=participants)

    def evaluate_exercise(self, exercise_id) -> ExerciseScore:
        score = self.exercise_framework.evaluate(exercise_id)
        exercise = self.exercise_framework.get_exercise(exercise_id)
        if exercise:
            for participant in exercise.participants:
                officer_id = participant.get("officer_id")
                if officer_id and self.training_portal.officers.get_officer(officer_id):
                    self.training_portal.officers.record_exercise(officer_id, exercise_id, score.overall_score)
        return score

    def create_scenario(self, method: str, **kwargs) -> dict:
        if method == "orbat":
            return self.scenario_author.create_from_orbat(
                kwargs["blue_force_id"], kwargs["red_force_id"], terrain=kwargs.get("terrain", "desert")
            )
        if method == "brief":
            return self.scenario_author.create_from_brief(kwargs["brief"])
        if method == "msdl":
            return self.scenario_author.create_from_msdl(kwargs["msdl_xml"])
        if method == "template":
            templates = self.scenario_author.get_scenario_templates()
            return {"template": templates[0]}
        raise ValueError("unsupported scenario creation method")

    def get_officer(self, officer_id):
        return self.training_portal.officers.get_officer(officer_id)

    def register_officer(self, *args, **kwargs):
        return self.training_portal.officers.register_officer(*args, **kwargs)

    def assign_course(self, officer_id, course_id, due_date=None):
        return self.training_portal.assign_course(officer_id, course_id, due_date)

    def assign_exercise(self, officer_id, exercise_id):
        return self.training_portal.assign_exercise(officer_id, exercise_id)

    def get_portal_overview(self):
        return self.training_portal.get_portal_overview()

    def get_readiness(self, unit):
        return self.training_portal.get_unit_readiness(unit)

    def get_replay(self, session_id) -> List[dict]:
        session = self.wargame_suite.engine.get_session(session_id)
        if session is None:
            raise ValueError("session not found")
        self.battle_visualizer.register_session(session)
        return self.battle_visualizer.generate_replay(session)

    def generate_training_report(self) -> str:
        return self.training_portal.generate_training_report()

    def health_check(self) -> dict:
        return {
            "status": "operational",
            "wargaming": self.wargame_suite.engine.health_check(),
            "exercises": self.exercise_framework.health_check(),
            "training": self.training_portal.health_check(),
            "cyber_range": self.cyber_range.health_check(),
        }
