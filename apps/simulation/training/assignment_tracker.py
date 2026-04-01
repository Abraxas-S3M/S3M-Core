"""Assignment lifecycle tracking for officer workloads."""

from __future__ import annotations

from datetime import datetime, timezone
from statistics import mean
from typing import Dict, List
from uuid import uuid4

from apps.simulation.models import Assignment


class AssignmentTracker:
    """Tracks assignments for courses, exercises, and wargames."""

    def __init__(self):
        self._assignments: Dict[str, Assignment] = {}

    def assign(self, officer_id, course_id=None, exercise_id=None, wargame_id=None, due_date=None) -> Assignment:
        assignment = Assignment(
            assignment_id=f"asg-{uuid4().hex[:10]}",
            officer_id=str(officer_id),
            course_id=course_id,
            exercise_id=exercise_id,
            wargame_id=wargame_id,
            assigned_at=datetime.now(timezone.utc),
            due_date=due_date,
            status="assigned",
        )
        self._assignments[assignment.assignment_id] = assignment
        return assignment

    def get_assignments(self, officer_id=None, status=None) -> List[Assignment]:
        rows = list(self._assignments.values())
        if officer_id is not None:
            rows = [row for row in rows if row.officer_id == officer_id]
        if status is not None:
            rows = [row for row in rows if row.status == status]
        return rows

    def start_assignment(self, assignment_id):
        assignment = self._assignments[assignment_id]
        assignment.status = "in_progress"

    def complete_assignment(self, assignment_id, score: float):
        assignment = self._assignments[assignment_id]
        assignment.status = "completed"
        assignment.score = float(score)

    def get_overdue(self) -> List[Assignment]:
        overdue = []
        for assignment in self._assignments.values():
            if assignment.is_overdue():
                assignment.status = "overdue"
                overdue.append(assignment)
        return overdue

    def get_completion_rate(self, officer_id: str = None) -> float:
        rows = self.get_assignments(officer_id=officer_id)
        if not rows:
            return 0.0
        completed = len([row for row in rows if row.status == "completed"])
        return round((completed / len(rows)) * 100.0, 2)

    def get_stats(self) -> dict:
        rows = list(self._assignments.values())
        scores = [row.score for row in rows if row.score is not None]
        return {
            "total": len(rows),
            "completed": len([r for r in rows if r.status == "completed"]),
            "overdue": len([r for r in rows if r.status == "overdue"]),
            "completion_rate": self.get_completion_rate(),
            "avg_score": round(mean(scores), 2) if scores else 0.0,
        }
