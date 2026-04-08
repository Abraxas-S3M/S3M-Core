"""Action board task prioritization for command workspace."""

from __future__ import annotations

from datetime import datetime, timezone
from threading import RLock
from typing import Dict, List, Literal, Optional
from uuid import uuid4

from pydantic import BaseModel, Field

from src.api.gui_bridge.models.gui_schemas import GUIActionItem

TaskStatus = Literal["pending", "active", "complete"]

# TaskWarrior-inspired coefficients tuned for tactical task triage.
_URGENCY_WEIGHT = 2.0
_IMPACT_WEIGHT = 1.5
_AGE_HOURS_WEIGHT = 0.1


class ActionTask(BaseModel):
    id: str
    title: str
    urgency: int = Field(ge=1, le=5)
    impact: int = Field(ge=1, le=5)
    assignee: Optional[str] = None
    status: TaskStatus = "pending"
    linked_decision_id: Optional[str] = None
    created_at: datetime


class ActionBoard:
    _tasks: Dict[str, ActionTask] = {}
    _lock = RLock()

    def add_task(
        self,
        title: str,
        urgency: int,
        impact: int,
        assignee: Optional[str] = None,
        status: TaskStatus = "pending",
        linked_decision_id: Optional[str] = None,
    ) -> GUIActionItem:
        task = ActionTask(
            id=f"TASK-{uuid4().hex[:8].upper()}",
            title=title.strip(),
            urgency=urgency,
            impact=impact,
            assignee=assignee.strip() if assignee else None,
            status=status,
            linked_decision_id=linked_decision_id.strip() if linked_decision_id else None,
            created_at=datetime.now(timezone.utc),
        )
        with self._lock:
            self._tasks[task.id] = task
        return self._to_gui_item(task)

    def get_tasks(self, status_filter: Optional[TaskStatus] = None) -> List[GUIActionItem]:
        with self._lock:
            tasks = list(self._tasks.values())

        if status_filter:
            tasks = [task for task in tasks if task.status == status_filter]

        tasks.sort(key=lambda task: task.created_at, reverse=True)
        return [self._to_gui_item(task) for task in tasks]

    def update_task(
        self,
        task_id: str,
        title: Optional[str] = None,
        urgency: Optional[int] = None,
        impact: Optional[int] = None,
        assignee: Optional[str] = None,
        status: Optional[TaskStatus] = None,
        linked_decision_id: Optional[str] = None,
    ) -> Optional[GUIActionItem]:
        with self._lock:
            existing = self._tasks.get(task_id)
            if not existing:
                return None

            payload = existing.model_dump()
            if title is not None:
                payload["title"] = title.strip()
            if urgency is not None:
                payload["urgency"] = urgency
            if impact is not None:
                payload["impact"] = impact
            if assignee is not None:
                payload["assignee"] = assignee.strip() if assignee else None
            if status is not None:
                payload["status"] = status
            if linked_decision_id is not None:
                payload["linked_decision_id"] = linked_decision_id.strip() if linked_decision_id else None

            updated = ActionTask(**payload)
            self._tasks[task_id] = updated

        return self._to_gui_item(updated)

    def get_prioritized(self) -> List[GUIActionItem]:
        with self._lock:
            tasks = list(self._tasks.values())

        tasks.sort(
            key=lambda task: (
                -self._compute_urgency_score(task),
                task.created_at,
            )
        )
        return [self._to_gui_item(task) for task in tasks]

    def _compute_urgency_score(self, task: ActionTask) -> float:
        age_hours = max(
            (datetime.now(timezone.utc) - task.created_at).total_seconds() / 3600.0,
            0.0,
        )
        return (
            (task.urgency * _URGENCY_WEIGHT)
            + (task.impact * _IMPACT_WEIGHT)
            + (age_hours * _AGE_HOURS_WEIGHT)
        )

    def _to_gui_item(self, task: ActionTask) -> GUIActionItem:
        return GUIActionItem(
            id=task.id,
            title=task.title,
            urgency=task.urgency,
            impact=task.impact,
            urgencyScore=round(self._compute_urgency_score(task), 3),
            assignee=task.assignee,
            status=task.status,
            linkedDecisionId=task.linked_decision_id,
            createdAt=task.created_at.isoformat(),
        )
