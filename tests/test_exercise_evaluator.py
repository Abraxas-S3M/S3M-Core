from apps.simulation.exercises.exercise_builder import ExerciseBuilder
from apps.simulation.exercises.exercise_evaluator import ExerciseEvaluator


def _exercise():
    builder = ExerciseBuilder()
    ex = builder.create_tabletop("Eval", "Brief", [{"officer_id": "off-1", "role": "cmd"}])
    for phase in ex.phases:
        phase.status = "completed"
    return ex


def test_evaluate_scores_and_overall():
    evaluator = ExerciseEvaluator()
    score = evaluator.evaluate(_exercise())
    assert score.phase_scores
    assert score.overall_score >= 0


def test_grade_thresholds():
    evaluator = ExerciseEvaluator()
    assert evaluator._grade(95) == "A+"
    assert evaluator._grade(70) == "B"
    assert evaluator._grade(50) == "F"


def test_strengths_and_weaknesses_present():
    evaluator = ExerciseEvaluator()
    score = evaluator.evaluate(_exercise())
    assert score.strengths
    assert score.weaknesses


def test_llm_fallback_feedback_present():
    evaluator = ExerciseEvaluator()
    score = evaluator.evaluate(_exercise())
    assert isinstance(score.llm_feedback, str)
    assert len(score.llm_feedback) > 0
