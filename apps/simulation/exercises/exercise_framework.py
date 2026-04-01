"""End-to-end exercise management facade."""

from __future__ import annotations

from typing import Dict, List, Optional

from apps.simulation.exercises.exercise_builder import ExerciseBuilder
from apps.simulation.exercises.exercise_evaluator import ExerciseEvaluator
from apps.simulation.models import Exercise, ExerciseScore


class ExerciseFramework:
    """Stores exercises and applies evaluation workflows."""

    def __init__(self):
        self.builder = ExerciseBuilder()
        self.evaluator = ExerciseEvaluator()
        self._exercises: Dict[str, Exercise] = {}
        self._scores: Dict[str, ExerciseScore] = {}

    def create_exercise(self, *args, **kwargs) -> Exercise:
        exercise = self.builder.create_exercise(*args, **kwargs)
        self._exercises[exercise.exercise_id] = exercise
        return exercise

    def create_tabletop(self, *args, **kwargs) -> Exercise:
        exercise = self.builder.create_tabletop(*args, **kwargs)
        self._exercises[exercise.exercise_id] = exercise
        return exercise

    def create_command_post(self, *args, **kwargs) -> Exercise:
        exercise = self.builder.create_command_post(*args, **kwargs)
        self._exercises[exercise.exercise_id] = exercise
        return exercise

    def create_cyber_exercise(self, *args, **kwargs) -> Exercise:
        exercise = self.builder.create_cyber_exercise(*args, **kwargs)
        self._exercises[exercise.exercise_id] = exercise
        return exercise

    def get_exercise(self, exercise_id: str) -> Optional[Exercise]:
        return self._exercises.get(exercise_id)

    def get_exercises(self) -> List[Exercise]:
        return list(self._exercises.values())

    def evaluate(self, exercise_id: str) -> ExerciseScore:
        exercise = self._exercises.get(exercise_id)
        if exercise is None:
            raise ValueError("exercise not found")
        score = self.evaluator.evaluate(exercise)
        self._scores[exercise_id] = score
        exercise.final_score = score.overall_score
        exercise.status = "completed"
        return score

    def get_score(self, exercise_id: str) -> Optional[ExerciseScore]:
        return self._scores.get(exercise_id)

    def health_check(self) -> dict:
        return {
            "status": "operational",
            "exercises": len(self._exercises),
            "scores": len(self._scores),
        }
