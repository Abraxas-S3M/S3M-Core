"""
S3M Priority-Based Compute Allocator
====================================
Manages scarce edge CPU/memory by prioritizing tactical workloads based
on urgency, deadlines, and mission-critical preemption rules.
"""

from __future__ import annotations

import heapq
import threading
import time
import uuid
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple

from pydantic import BaseModel, Field


class TaskPriority(str, Enum):
    CRITICAL = "critical"  # Life safety, engagement, collision avoidance
    HIGH = "high"  # Threat assessment, navigation
    MEDIUM = "medium"  # Routine inference, reporting
    LOW = "low"  # Background analytics
    BACKGROUND = "background"  # Data sync, housekeeping


PRIORITY_SCORES = {
    TaskPriority.CRITICAL: 100,
    TaskPriority.HIGH: 75,
    TaskPriority.MEDIUM: 50,
    TaskPriority.LOW: 25,
    TaskPriority.BACKGROUND: 10,
}


class ComputeTask(BaseModel):
    """A compute task requesting edge resources."""

    task_id: str = Field(default_factory=lambda: str(uuid.uuid4())[:12])
    name: str = ""
    priority: TaskPriority = TaskPriority.MEDIUM
    cpu_cores_needed: float = Field(default=1.0, ge=0.1)
    memory_mb_needed: float = Field(default=256.0, ge=1.0)
    deadline_ms: Optional[float] = Field(default=None, gt=0.0)
    submitted_at: float = Field(default_factory=time.time)
    metadata: Dict[str, Any] = Field(default_factory=dict)


class AllocationResult(BaseModel):
    """Result of resource allocation attempt."""

    task_id: str
    allocated: bool
    allocated_cores: float = 0.0
    allocated_memory_mb: float = 0.0
    preempted_tasks: List[str] = Field(default_factory=list)
    reason: str = ""
    wait_ms: float = 0.0


class PriorityAllocator:
    """
    Priority-aware resource allocator for austere edge nodes.

    Features:
    - Priority queue with deterministic ordering
    - Preemption of lower-priority active tasks
    - Live resource utilization accounting
    """

    def __init__(
        self,
        total_cores: float = 4.0,
        total_memory_mb: float = 16384.0,
        preemption_enabled: bool = True,
    ) -> None:
        if total_cores <= 0.0:
            raise ValueError("total_cores must be > 0")
        if total_memory_mb <= 0.0:
            raise ValueError("total_memory_mb must be > 0")
        self._total_cores = float(total_cores)
        self._total_memory = float(total_memory_mb)
        self._used_cores = 0.0
        self._used_memory = 0.0
        self._active_tasks: Dict[str, ComputeTask] = {}
        self._queue: List[Tuple[int, float, int, ComputeTask]] = []
        self._queue_seq = 0
        self._preemption = bool(preemption_enabled)
        self._allocation_log: List[AllocationResult] = []
        self._lock = threading.Lock()

    def submit(self, task: ComputeTask) -> AllocationResult:
        """Submit a task for immediate allocation or queueing."""
        with self._lock:
            score = PRIORITY_SCORES.get(task.priority, 50)
            score += self._deadline_bonus(task.deadline_ms)

            cores_free = self._total_cores - self._used_cores
            mem_free = self._total_memory - self._used_memory

            if task.cpu_cores_needed <= cores_free and task.memory_mb_needed <= mem_free:
                return self._allocate(task)

            if self._preemption and score > 50:
                preempted_result = self._try_preempt(task, score)
                if preempted_result is not None:
                    return preempted_result

            self._queue_seq += 1
            heapq.heappush(self._queue, (-score, task.submitted_at, self._queue_seq, task))
            result = AllocationResult(
                task_id=task.task_id,
                allocated=False,
                reason=(
                    "Queued: insufficient resources "
                    f"(need {task.cpu_cores_needed} cores, {task.memory_mb_needed}MB)"
                ),
            )
            self._allocation_log.append(result)
            return result

    def release(self, task_id: str) -> bool:
        """Release resources held by a completed task."""
        with self._lock:
            task = self._active_tasks.pop(task_id, None)
            if task is None:
                return False

            self._used_cores = max(0.0, self._used_cores - task.cpu_cores_needed)
            self._used_memory = max(0.0, self._used_memory - task.memory_mb_needed)
            self._process_queue()
            return True

    def _allocate(self, task: ComputeTask) -> AllocationResult:
        self._active_tasks[task.task_id] = task
        self._used_cores += task.cpu_cores_needed
        self._used_memory += task.memory_mb_needed
        result = AllocationResult(
            task_id=task.task_id,
            allocated=True,
            allocated_cores=task.cpu_cores_needed,
            allocated_memory_mb=task.memory_mb_needed,
            reason="Allocated immediately",
        )
        self._allocation_log.append(result)
        return result

    def _try_preempt(self, task: ComputeTask, score: int) -> Optional[AllocationResult]:
        """Preempt lower-priority active tasks to admit urgent tactical task."""
        candidates = sorted(
            self._active_tasks.values(),
            key=lambda t: PRIORITY_SCORES.get(t.priority, 50),
        )
        freed_cores = 0.0
        freed_mem = 0.0
        to_preempt: List[ComputeTask] = []

        for candidate in candidates:
            candidate_score = PRIORITY_SCORES.get(candidate.priority, 50)
            if candidate_score >= score:
                break
            to_preempt.append(candidate)
            freed_cores += candidate.cpu_cores_needed
            freed_mem += candidate.memory_mb_needed

            available_cores = (self._total_cores - self._used_cores) + freed_cores
            available_mem = (self._total_memory - self._used_memory) + freed_mem
            if available_cores >= task.cpu_cores_needed and available_mem >= task.memory_mb_needed:
                preempted_ids: List[str] = []
                for preempted in to_preempt:
                    self._active_tasks.pop(preempted.task_id, None)
                    self._used_cores -= preempted.cpu_cores_needed
                    self._used_memory -= preempted.memory_mb_needed
                    preempted_ids.append(preempted.task_id)

                    preempted_score = PRIORITY_SCORES.get(preempted.priority, 50)
                    self._queue_seq += 1
                    heapq.heappush(
                        self._queue,
                        (-preempted_score, preempted.submitted_at, self._queue_seq, preempted),
                    )

                self._used_cores = max(0.0, self._used_cores)
                self._used_memory = max(0.0, self._used_memory)
                result = self._allocate(task)
                result.preempted_tasks = preempted_ids
                result.reason = f"Preempted {len(preempted_ids)} lower-priority tasks"
                return result
        return None

    def _process_queue(self) -> None:
        new_queue: List[Tuple[int, float, int, ComputeTask]] = []
        while self._queue:
            neg_score, submitted_at, seq, queued_task = heapq.heappop(self._queue)
            cores_free = self._total_cores - self._used_cores
            mem_free = self._total_memory - self._used_memory
            if queued_task.cpu_cores_needed <= cores_free and queued_task.memory_mb_needed <= mem_free:
                self._allocate(queued_task)
            else:
                new_queue.append((neg_score, submitted_at, seq, queued_task))
        self._queue = new_queue
        heapq.heapify(self._queue)

    def get_utilization(self) -> Dict[str, float]:
        with self._lock:
            return {
                "cpu_used": self._used_cores,
                "cpu_total": self._total_cores,
                "cpu_pct": self._used_cores / self._total_cores * 100.0,
                "memory_used_mb": self._used_memory,
                "memory_total_mb": self._total_memory,
                "memory_pct": self._used_memory / self._total_memory * 100.0,
                "active_tasks": float(len(self._active_tasks)),
                "queued_tasks": float(len(self._queue)),
            }

    @staticmethod
    def _deadline_bonus(deadline_ms: Optional[float]) -> int:
        if deadline_ms is None:
            return 0
        if deadline_ms <= 250.0:
            return 20
        if deadline_ms <= 1_000.0:
            return 10
        return 0
