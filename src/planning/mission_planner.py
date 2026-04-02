"""
S3M Multi-Domain Mission Planner — Gap 4 of 7
Combinatorial task optimization using OR-Tools CP-SAT.
LLM co-planner integration via the existing S3M Orchestrator.
Falls back gracefully if or-tools not installed.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger("s3m.planning")

try:
    from ortools.sat.python import cp_model

    ORTOOLS_AVAILABLE = True
except ImportError:
    ORTOOLS_AVAILABLE = False
    logger.warning("or-tools not installed — falling back to greedy planner")


# ─── Domain Types ─────────────────────────────────────────────────────────────


class MissionDomain(str, Enum):
    AIR = "AIR"
    LAND = "LAND"
    SEA = "SEA"
    CYBER = "CYBER"
    SPACE = "SPACE"


class TaskPriority(int, Enum):
    CRITICAL = 1
    HIGH = 2
    MEDIUM = 3
    LOW = 4


@dataclass
class Asset:
    asset_id: str
    callsign: str
    domains: List[MissionDomain]
    readiness_score: float  # 0–1
    endurance_hours: float
    speed_kmh: float
    lat: float
    lon: float


@dataclass
class MissionTask:
    task_id: str
    description_en: str
    description_ar: str
    domain: MissionDomain
    priority: TaskPriority
    required_assets: int  # min assets needed
    duration_hours: float
    lat: float
    lon: float
    time_window_start: int = 0  # hours from now
    time_window_end: int = 24


@dataclass
class TaskAssignment:
    task_id: str
    asset_ids: List[str]
    start_hour: int
    end_hour: float
    domain: MissionDomain
    priority: TaskPriority
    feasibility_score: float


@dataclass
class MissionPlan:
    plan_id: str
    generated_at: str
    assignments: List[TaskAssignment]
    unassigned_tasks: List[str]
    coverage_pct: float
    llm_assessment: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "plan_id": self.plan_id,
            "generated_at": self.generated_at,
            "coverage_pct": self.coverage_pct,
            "assignments": [
                {
                    "task_id": a.task_id,
                    "asset_ids": a.asset_ids,
                    "start_hour": a.start_hour,
                    "end_hour": a.end_hour,
                    "domain": a.domain.value,
                    "priority": int(a.priority.value),
                    "feasibility": a.feasibility_score,
                }
                for a in self.assignments
            ],
            "unassigned_tasks": self.unassigned_tasks,
            "llm_assessment": self.llm_assessment,
        }


# ─── OR-Tools Optimizer ───────────────────────────────────────────────────────


class ORToolsPlanner:
    """CP-SAT based combinatorial mission optimizer."""

    HORIZON_H = 24  # planning horizon in hours
    SCALE = 100  # fixed-point scale for float→int conversion

    def _is_asset_capable(self, task: MissionTask, asset: Asset) -> bool:
        return (
            task.domain in asset.domains
            and asset.readiness_score >= 0.5
            and asset.endurance_hours >= task.duration_hours
            and task.time_window_start <= task.time_window_end
            and task.time_window_start <= self.HORIZON_H
            and task.duration_hours > 0
        )

    def plan(
        self,
        tasks: List[MissionTask],
        assets: List[Asset],
    ) -> Tuple[List[TaskAssignment], List[str]]:
        if not tasks:
            return [], []
        if not assets:
            return [], [t.task_id for t in tasks]
        if not ORTOOLS_AVAILABLE:
            return self._greedy_fallback(tasks, assets)

        model = cp_model.CpModel()
        task_vars: Dict[Tuple[int, int], Any] = {}  # (task_idx, asset_idx) → BoolVar
        task_selected: Dict[int, Any] = {}  # task_idx -> BoolVar
        assignments: List[TaskAssignment] = []
        unassigned: List[str] = []

        capable: Dict[int, List[int]] = {}
        for ti, task in enumerate(tasks):
            capable[ti] = [ai for ai, asset in enumerate(assets) if self._is_asset_capable(task, asset)]

        # Decision variables for assignment edges and task activation.
        for ti, task in enumerate(tasks):
            task_selected[ti] = model.NewBoolVar(f"task_selected_{ti}")
            for ai in capable[ti]:
                task_vars[(ti, ai)] = model.NewBoolVar(f"x_{ti}_{ai}")

            caps = [task_vars[(ti, ai)] for ai in capable[ti]]
            req = max(1, int(task.required_assets))
            if caps:
                # Tactical context: either fully crew a task or skip it to avoid
                # committing partial force packages that cannot execute effectively.
                model.Add(sum(caps) >= req * task_selected[ti])
                model.Add(sum(caps) <= len(caps) * task_selected[ti])
            else:
                model.Add(task_selected[ti] == 0)

        # Endurance budget per asset (scaled integer linear constraint).
        for ai, asset in enumerate(assets):
            used_pairs = [(ti, task_vars[(ti, ai)]) for ti in range(len(tasks)) if (ti, ai) in task_vars]
            if not used_pairs:
                continue
            lhs_terms = []
            for ti, decision in used_pairs:
                dur_i = max(1, int(round(tasks[ti].duration_hours * self.SCALE)))
                lhs_terms.append(decision * dur_i)
            endurance_i = max(0, int(round(asset.endurance_hours * self.SCALE)))
            model.Add(sum(lhs_terms) <= endurance_i)

        # Objective: maximize priority-weighted completed tasks.
        obj_terms = []
        for ti, task in enumerate(tasks):
            weight = (5 - int(task.priority.value)) * self.SCALE
            obj_terms.append(task_selected[ti] * weight)
        model.Maximize(sum(obj_terms))

        solver = cp_model.CpSolver()
        solver.parameters.max_time_in_seconds = 5.0
        status = solver.Solve(model)

        if status in (cp_model.OPTIMAL, cp_model.FEASIBLE):
            for ti, task in enumerate(tasks):
                is_selected = solver.Value(task_selected[ti]) == 1
                assigned_assets = [
                    assets[ai].asset_id
                    for ai in capable[ti]
                    if (ti, ai) in task_vars and solver.Value(task_vars[(ti, ai)]) == 1
                ]
                if is_selected and assigned_assets:
                    req = max(1, int(task.required_assets))
                    assignments.append(
                        TaskAssignment(
                            task_id=task.task_id,
                            asset_ids=assigned_assets,
                            start_hour=task.time_window_start,
                            end_hour=task.time_window_start + task.duration_hours,
                            domain=task.domain,
                            priority=task.priority,
                            feasibility_score=min(1.0, len(assigned_assets) / req),
                        )
                    )
                else:
                    unassigned.append(task.task_id)
        else:
            unassigned = [t.task_id for t in tasks]

        return assignments, unassigned

    def _greedy_fallback(
        self, tasks: List[MissionTask], assets: List[Asset]
    ) -> Tuple[List[TaskAssignment], List[str]]:
        """Priority-order greedy when OR-Tools unavailable."""
        sorted_tasks = sorted(tasks, key=lambda t: t.priority.value)
        asset_hours: Dict[str, float] = {a.asset_id: a.endurance_hours for a in assets}
        assignments: List[TaskAssignment] = []
        unassigned: List[str] = []

        for task in sorted_tasks:
            capable = [
                a
                for a in assets
                if task.domain in a.domains
                and a.readiness_score >= 0.5
                and asset_hours.get(a.asset_id, 0.0) >= task.duration_hours
                and task.duration_hours > 0
            ]
            req = max(1, int(task.required_assets))
            selected = capable[:req]
            if len(selected) >= req:
                for a in selected:
                    asset_hours[a.asset_id] -= task.duration_hours
                assignments.append(
                    TaskAssignment(
                        task_id=task.task_id,
                        asset_ids=[a.asset_id for a in selected],
                        start_hour=task.time_window_start,
                        end_hour=task.time_window_start + task.duration_hours,
                        domain=task.domain,
                        priority=task.priority,
                        feasibility_score=1.0,
                    )
                )
            else:
                unassigned.append(task.task_id)

        return assignments, unassigned


# ─── Mission Planner (public facade) ─────────────────────────────────────────


class MultiDomainMissionPlanner:
    """
    Usage:
        planner = MultiDomainMissionPlanner()
        plan = planner.generate_plan(tasks, assets)
    """

    def __init__(self, use_llm: bool = True) -> None:
        self._optimizer = ORToolsPlanner()
        self._use_llm = use_llm

    def generate_plan(
        self, tasks: List[MissionTask], assets: List[Asset]
    ) -> MissionPlan:
        from uuid import uuid4

        assignments, unassigned = self._optimizer.plan(tasks, assets)
        coverage = len(assignments) / len(tasks) * 100 if tasks else 0.0
        llm_note = self._llm_red_team(assignments, unassigned) if self._use_llm else None
        return MissionPlan(
            plan_id=str(uuid4()),
            generated_at=datetime.now(timezone.utc).isoformat(),
            assignments=assignments,
            unassigned_tasks=unassigned,
            coverage_pct=round(coverage, 1),
            llm_assessment=llm_note,
        )

    def _llm_red_team(
        self, assignments: List[TaskAssignment], unassigned: List[str]
    ) -> Optional[str]:
        """
        Pass plan summary to the S3M Orchestrator for LLM red-team assessment.
        Returns None if orchestrator unavailable.
        """
        try:
            from src.llm_core.orchestrator import Orchestrator

            orch = Orchestrator()
            summary = (
                f"Mission plan: {len(assignments)} tasks assigned, "
                f"{len(unassigned)} unassigned. "
                f"Unassigned task IDs: {unassigned}. "
                "Identify top 3 risk gaps and mitigation suggestions in English and Arabic."
            )
            result = orch.route_and_decide(summary)
            return result if isinstance(result, str) else str(result)
        except Exception as exc:  # pragma: no cover - defensive integration fallback
            logger.warning("LLM red-team unavailable: %s", exc)
            return None
