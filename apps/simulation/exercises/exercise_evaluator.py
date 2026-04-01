"""Exercise scoring engine with weighted military training metrics."""

from __future__ import annotations

from datetime import datetime, timezone
from statistics import mean
from typing import List
from uuid import uuid4

from apps.simulation.models import Exercise, ExerciseScore
from src.llm_core.engine_registry import TaskDomain
from src.llm_core.orchestrator import Orchestrator, QueryRequest


class ExerciseEvaluator:
    """Computes phase and overall exercise scores plus qualitative feedback."""

    def __init__(self):
        self._orchestrator = Orchestrator()

    def _grade(self, score: float) -> str:
        if score >= 95:
            return "A+"
        if score >= 85:
            return "A"
        if score >= 75:
            return "B+"
        if score >= 65:
            return "B"
        if score >= 55:
            return "C"
        return "F"

    def _llm_feedback(self, summary: str, strengths: List[str], weaknesses: List[str]) -> str:
        prompt = (
            f"Evaluate this officer's exercise performance: {summary}. Key decisions: n/a. "
            f"Strengths: {strengths}. Areas for improvement: {weaknesses}. "
            "Provide constructive feedback and development recommendations."
        )
        try:
            response = self._orchestrator.process(QueryRequest(prompt=prompt, domain=TaskDomain.REASONING))
            text = getattr(response, "text", "") or ""
            if text.strip():
                return text.strip()
        except Exception:
            pass
        return "Feedback template: reinforce mission analysis, decision speed, and objective tracking discipline."

    def evaluate(self, exercise: Exercise) -> ExerciseScore:
        phase_scores = {}
        for phase in exercise.phases:
            obj_met = 1.0 if phase.status == "completed" else 0.6 if phase.status == "active" else 0.5
            wg_perf = 0.7 if phase.wargame_ids else 0.6
            planned = max(1, int(phase.duration_minutes))
            timeliness = 1.0 if planned <= 120 else 0.8
            decision_quality = 0.75 if "decision" in phase.name.lower() else 0.7
            score = (
                obj_met * 40.0
                + wg_perf * 30.0
                + timeliness * 15.0
                + decision_quality * 15.0
            )
            phase_scores[phase.phase_id] = round(max(0.0, min(100.0, score)), 2)

        overall = round(mean(phase_scores.values()) if phase_scores else 0.0, 2)
        grade = self._grade(overall)

        strengths = ["Objective execution"]
        weaknesses = ["Decision speed under pressure"]
        for pid, score in phase_scores.items():
            if score >= 80:
                strengths.append(f"Strong phase performance ({pid})")
            elif score < 65:
                weaknesses.append(f"Needs improvement in phase {pid}")

        officer_id = "unknown"
        if exercise.participants:
            officer_id = str(exercise.participants[0].get("officer_id", "unknown"))

        summary = f"overall={overall}, grade={grade}, phase_scores={phase_scores}"
        feedback = self._llm_feedback(summary, strengths, weaknesses)

        return ExerciseScore(
            score_id=f"score-{uuid4().hex[:10]}",
            exercise_id=exercise.exercise_id,
            officer_id=officer_id,
            phase_scores=phase_scores,
            overall_score=overall,
            grade=grade,
            strengths=strengths,
            weaknesses=weaknesses,
            llm_feedback=feedback,
            scored_at=datetime.now(timezone.utc),
        )

    def evaluate_batch(self, exercises: List[Exercise], officer_id: str) -> dict:
        scores = [self.evaluate(ex).overall_score for ex in exercises if any(p.get("officer_id") == officer_id for p in ex.participants)]
        if not scores:
            return {"officer_id": officer_id, "trend": "stable", "scores": []}
        trend = "stable"
        if len(scores) >= 2:
            if scores[-1] > scores[0] + 3:
                trend = "improving"
            elif scores[-1] < scores[0] - 3:
                trend = "declining"
        return {
            "officer_id": officer_id,
            "scores": scores,
            "average": round(mean(scores), 2),
            "trend": trend,
        }
