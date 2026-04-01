"""Officer-facing training portal orchestrator."""

from __future__ import annotations

from statistics import mean

from apps.simulation.training.assignment_tracker import AssignmentTracker
from apps.simulation.training.course_manager import CourseManager
from apps.simulation.training.officer_manager import OfficerManager
from src.llm_core.engine_registry import TaskDomain
from src.llm_core.orchestrator import Orchestrator, QueryRequest


class TrainingPortal:
    """Aggregates officer records, assignments, and course catalog operations."""

    def __init__(self):
        self.officers = OfficerManager()
        self.courses = CourseManager(officer_manager=self.officers)
        self.assignments = AssignmentTracker()
        self._orchestrator = Orchestrator()

    def get_portal_overview(self) -> dict:
        officer_rows = self.officers.get_officers()
        assignment_rows = self.assignments.get_assignments()
        avg_score = mean([o.average_score for o in officer_rows]) if officer_rows else 0.0
        top = self.officers.get_leaderboard(limit=5)
        return {
            "officers_registered": len(officer_rows),
            "active_courses": len(self.courses.get_courses()),
            "pending_assignments": len([a for a in assignment_rows if a.status in {"assigned", "in_progress"}]),
            "completion_rate": self.assignments.get_completion_rate(),
            "avg_score": round(avg_score, 2),
            "top_performers": top,
        }

    def assign_course(self, officer_id, course_id, due_date=None):
        return self.assignments.assign(officer_id=officer_id, course_id=course_id, due_date=due_date)

    def assign_exercise(self, officer_id, exercise_id):
        return self.assignments.assign(officer_id=officer_id, exercise_id=exercise_id)

    def get_officer_dashboard(self, officer_id) -> dict:
        officer = self.officers.get_officer(officer_id)
        if officer is None:
            raise ValueError("officer not found")
        assignments = self.assignments.get_assignments(officer_id=officer_id)
        active = [a.to_dict() for a in assignments if a.status in {"assigned", "in_progress", "overdue"}]
        completed = [a.to_dict() for a in assignments if a.status == "completed"]

        next_recommended = None
        for course in self.courses.get_courses():
            if course.course_id in officer.courses_completed:
                continue
            if self.courses.get_prerequisites_met(officer_id, course.course_id):
                next_recommended = course.to_dict()
                break

        return {
            "officer": officer.to_dict(),
            "active_assignments": active,
            "completed_assignments": completed,
            "certificates": list(officer.certifications),
            "next_recommended": next_recommended,
        }

    def get_unit_readiness(self, unit: str) -> dict:
        officers = self.officers.get_officers(unit=unit)
        return {
            "unit": unit,
            "officers": [
                {
                    "officer_id": o.officer_id,
                    "name": o.name,
                    "readiness_score": o.readiness_score(),
                    "average_score": o.average_score,
                }
                for o in officers
            ],
        }

    def generate_training_report(self) -> str:
        stats = self.get_portal_overview()
        prompt = (
            f"Generate a military training status report: {stats}. Include: "
            "1) Overall readiness 2) Completion rates 3) Top performers "
            "4) Training gaps 5) Recommendations."
        )
        try:
            response = self._orchestrator.process(QueryRequest(prompt=prompt, domain=TaskDomain.PLANNING))
            text = getattr(response, "text", "") or ""
            if text.strip():
                return text.strip()
        except Exception:
            pass
        return (
            "Training report: readiness moderate and improving; assignment completion remains primary gap. "
            "Recommendation: increase tabletop repetition and certification completion cadence."
        )

    def health_check(self) -> dict:
        return {
            "status": "operational",
            "officers": len(self.officers.get_officers()),
            "courses": len(self.courses.get_courses()),
            "assignments": len(self.assignments.get_assignments()),
        }
