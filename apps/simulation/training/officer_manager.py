"""Officer records and readiness analytics management."""

from __future__ import annotations

from statistics import mean
from typing import Dict, List, Optional
from uuid import uuid4

from apps.simulation.models import OfficerRecord
from src.llm_core.engine_registry import TaskDomain
from src.llm_core.orchestrator import Orchestrator, QueryRequest


class OfficerManager:
    """Maintains officer performance history across exercises, wargames, and courses."""

    def __init__(self):
        self._officers: Dict[str, OfficerRecord] = {}
        self._scores: Dict[str, List[float]] = {}
        self._orchestrator = Orchestrator()

    def register_officer(self, name, rank, unit, specialization) -> OfficerRecord:
        officer = OfficerRecord(
            officer_id=f"off-{uuid4().hex[:10]}",
            name=str(name),
            rank=str(rank),
            unit=str(unit),
            specialization=str(specialization),
        )
        self._officers[officer.officer_id] = officer
        self._scores[officer.officer_id] = []
        return officer

    def get_officer(self, officer_id) -> Optional[OfficerRecord]:
        return self._officers.get(officer_id)

    def get_officers(self, rank=None, unit=None, specialization=None) -> List[OfficerRecord]:
        officers = list(self._officers.values())
        if rank is not None:
            officers = [o for o in officers if o.rank == rank]
        if unit is not None:
            officers = [o for o in officers if o.unit == unit]
        if specialization is not None:
            officers = [o for o in officers if o.specialization == specialization]
        return officers

    def update_officer(self, officer_id, **kwargs):
        officer = self._officers.get(officer_id)
        if officer is None:
            return None
        for key, value in kwargs.items():
            if hasattr(officer, key):
                setattr(officer, key, value)
        return officer

    def _update_score(self, officer: OfficerRecord, score: float) -> None:
        history = self._scores.setdefault(officer.officer_id, [])
        history.append(float(score))
        officer.average_score = round(mean(history), 2)
        if len(history) >= 3:
            delta = history[-1] - history[-3]
            if delta > 3:
                officer.performance_trend = "improving"
            elif delta < -3:
                officer.performance_trend = "declining"
            else:
                officer.performance_trend = "stable"

    def record_exercise(self, officer_id, exercise_id, score: float):
        officer = self._officers[officer_id]
        if exercise_id not in officer.exercises_completed:
            officer.exercises_completed.append(exercise_id)
        self._update_score(officer, score)

    def record_wargame(self, officer_id, wargame_id, score: float):
        officer = self._officers[officer_id]
        if wargame_id not in officer.wargames_played:
            officer.wargames_played.append(wargame_id)
        self._update_score(officer, score)

    def record_course(self, officer_id, course_id, score: float, certification: str = None):
        officer = self._officers[officer_id]
        if course_id not in officer.courses_completed:
            officer.courses_completed.append(course_id)
        if certification and certification not in officer.certifications:
            officer.certifications.append(certification)
        self._update_score(officer, score)

    def get_officer_profile(self, officer_id) -> dict:
        officer = self._officers.get(officer_id)
        if officer is None:
            raise ValueError("officer not found")
        recommendation = "Continue combined-arms drills and decision-making exercises."
        prompt = (
            f"Create a concise officer development recommendation for {officer.name}. "
            f"Scores={self._scores.get(officer_id, [])}, trend={officer.performance_trend}, "
            f"strengths={officer.strengths}, development={officer.development_areas}."
        )
        try:
            response = self._orchestrator.process(QueryRequest(prompt=prompt, domain=TaskDomain.REASONING))
            text = getattr(response, "text", "") or ""
            if text.strip():
                recommendation = text.strip()
        except Exception:
            pass
        return {
            "record": officer.to_dict(),
            "score_history": list(self._scores.get(officer_id, [])),
            "readiness_score": officer.readiness_score(),
            "recommendation": recommendation,
        }

    def get_readiness_report(self) -> dict:
        buckets = {"90-100": 0, "75-89": 0, "60-74": 0, "<60": 0}
        cert_gap = 0
        for officer in self._officers.values():
            score = officer.readiness_score()
            if score >= 90:
                buckets["90-100"] += 1
            elif score >= 75:
                buckets["75-89"] += 1
            elif score >= 60:
                buckets["60-74"] += 1
            else:
                buckets["<60"] += 1
            if not officer.certifications:
                cert_gap += 1
        return {
            "officer_count": len(self._officers),
            "score_buckets": buckets,
            "officers_without_certification": cert_gap,
            "training_gaps": ["combined_arms", "c2", "cyber"] if cert_gap else [],
        }

    def get_leaderboard(self, limit=20) -> List[dict]:
        rows = []
        for officer in self._officers.values():
            rows.append(
                {
                    "officer_id": officer.officer_id,
                    "name": officer.name,
                    "rank": officer.rank,
                    "average_score": officer.average_score,
                    "readiness_score": officer.readiness_score(),
                }
            )
        rows.sort(key=lambda row: row["average_score"], reverse=True)
        return rows[: max(1, limit)]
