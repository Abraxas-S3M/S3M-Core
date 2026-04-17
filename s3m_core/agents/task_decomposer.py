"""Mission task decomposition utilities for agentic orchestration."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass(slots=True)
class SubTask:
    """Single executable unit in a mission plan."""

    task_id: str
    description: str
    required_tools: List[str] = field(default_factory=list)
    estimated_complexity: int = 1
    can_parallelize: bool = False
    depends_on: List[str] = field(default_factory=list)


@dataclass(slots=True)
class TaskPlan:
    """Decomposed mission plan with dependency and scheduling hints."""

    tasks: List[SubTask]
    dependencies: Dict[str, List[str]]
    parallelizable_groups: List[List[str]]
    estimated_steps: int
    estimated_time_seconds: int


class TaskDecomposer:
    """
    Break complex objectives into executable subtasks.

    Tactical context:
    A mission objective is transformed into a DAG so the orchestrator can
    parallelize independent actions while preserving sequencing constraints.
    """

    def __init__(self, model: Any) -> None:
        self.model = model

    def decompose(self, objective: str, context: Optional[str] = None) -> TaskPlan:
        """Return a validated task plan for the provided objective."""
        raw_plan = self._generate_with_model(objective=objective, context=context)
        tasks = self._normalize_tasks(raw_plan=raw_plan, objective=objective)
        dependencies = {task.task_id: list(task.depends_on) for task in tasks}
        self._validate_dag(dependencies=dependencies)
        parallelizable_groups = self._build_parallel_groups(tasks=tasks, dependencies=dependencies)
        estimated_steps = max(sum(max(task.estimated_complexity, 1) for task in tasks), len(tasks))
        estimated_time_seconds = estimated_steps * 30
        return TaskPlan(
            tasks=tasks,
            dependencies=dependencies,
            parallelizable_groups=parallelizable_groups,
            estimated_steps=estimated_steps,
            estimated_time_seconds=estimated_time_seconds,
        )

    def _generate_with_model(self, objective: str, context: Optional[str]) -> Dict[str, Any]:
        model = self.model
        if model is None:
            return {}

        decompose_fn = getattr(model, "decompose", None)
        if callable(decompose_fn):
            result = decompose_fn(objective=objective, context=context)
            if isinstance(result, dict):
                return result

        generate_fn = getattr(model, "generate_task_plan", None)
        if callable(generate_fn):
            result = generate_fn(objective=objective, context=context)
            if isinstance(result, dict):
                return result

        if callable(model):
            result = model(objective=objective, context=context)
            if isinstance(result, dict):
                return result

        return {}

    def _normalize_tasks(self, raw_plan: Dict[str, Any], objective: str) -> List[SubTask]:
        raw_tasks = raw_plan.get("tasks", []) if isinstance(raw_plan, dict) else []
        tasks: List[SubTask] = []
        for idx, raw_task in enumerate(raw_tasks):
            if not isinstance(raw_task, dict):
                continue
            task_id = str(raw_task.get("task_id") or f"task_{idx + 1}")
            description = str(raw_task.get("description") or f"Execute step {idx + 1}")
            required_tools = [str(item) for item in raw_task.get("required_tools", [])]
            complexity = int(raw_task.get("estimated_complexity", 1))
            can_parallelize = bool(raw_task.get("can_parallelize", False))
            depends_on = [str(item) for item in raw_task.get("depends_on", [])]
            tasks.append(
                SubTask(
                    task_id=task_id,
                    description=description,
                    required_tools=required_tools,
                    estimated_complexity=max(complexity, 1),
                    can_parallelize=can_parallelize,
                    depends_on=depends_on,
                )
            )

        if tasks:
            return tasks

        return self._fallback_tasks(objective=objective)

    def _fallback_tasks(self, objective: str) -> List[SubTask]:
        tokens = [chunk.strip() for chunk in objective.replace(" then ", ";").split(";") if chunk.strip()]
        if not tokens:
            tokens = [objective.strip() or "Clarify mission objective"]
        tasks: List[SubTask] = []
        for idx, token in enumerate(tokens):
            tasks.append(
                SubTask(
                    task_id=f"task_{idx + 1}",
                    description=token,
                    required_tools=[],
                    estimated_complexity=1,
                    can_parallelize=idx > 0,
                    depends_on=[] if idx == 0 else ["task_1"],
                )
            )
        return tasks

    def _validate_dag(self, dependencies: Dict[str, List[str]]) -> None:
        visited: Dict[str, int] = {}

        def visit(node: str) -> None:
            state = visited.get(node, 0)
            if state == 1:
                raise ValueError("Task dependencies contain a cycle")
            if state == 2:
                return
            visited[node] = 1
            for parent in dependencies.get(node, []):
                if parent not in dependencies:
                    raise ValueError(f"Task '{node}' depends on unknown task '{parent}'")
                visit(parent)
            visited[node] = 2

        for task_id in dependencies:
            visit(task_id)

    def _build_parallel_groups(
        self,
        *,
        tasks: List[SubTask],
        dependencies: Dict[str, List[str]],
    ) -> List[List[str]]:
        remaining = {task.task_id for task in tasks}
        done: set[str] = set()
        groups: List[List[str]] = []
        task_map = {task.task_id: task for task in tasks}

        while remaining:
            ready = [
                task_id
                for task_id in remaining
                if all(parent in done for parent in dependencies.get(task_id, []))
            ]
            if not ready:
                raise ValueError("No executable tasks available; dependency graph is invalid")

            parallel_ready = [task_id for task_id in ready if task_map[task_id].can_parallelize]
            serial_ready = [task_id for task_id in ready if task_id not in parallel_ready]

            if parallel_ready:
                groups.append(parallel_ready)
            for task_id in serial_ready:
                groups.append([task_id])

            for task_id in ready:
                remaining.remove(task_id)
                done.add(task_id)

        return groups
