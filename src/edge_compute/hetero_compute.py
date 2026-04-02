"""Heterogeneous compute scheduler for adaptive CPU/GPU dispatch."""

from __future__ import annotations

import time
from collections import defaultdict
from dataclasses import dataclass
from typing import Any, Callable, Dict, List

from src.edge_compute.models import DeviceType, OperationType, SchedulingPolicy


@dataclass
class ComputeCapabilities:
    gpu_available: bool = False
    gpu_name: str = "unavailable"
    cpu_cores: int = 4

    def to_dict(self) -> Dict[str, Any]:
        return {
            "gpu_available": self.gpu_available,
            "gpu_name": self.gpu_name,
            "cpu_cores": self.cpu_cores,
        }


class AdaptiveScheduler:
    """Track simplistic latency table for operation/device routing."""

    def __init__(self) -> None:
        self._policy_table: Dict[str, Dict[str, float]] = defaultdict(
            lambda: {"cpu": 0.0, "gpu": 0.0}
        )

    def choose(self, operation: OperationType, caps: ComputeCapabilities, policy: SchedulingPolicy) -> DeviceType:
        if policy == SchedulingPolicy.CPU_ONLY:
            return DeviceType.CPU
        if policy == SchedulingPolicy.GPU_PREFERRED and caps.gpu_available:
            return DeviceType.GPU
        if not caps.gpu_available:
            return DeviceType.CPU
        row = self._policy_table[operation.value]
        if row["gpu"] > 0.0 and row["cpu"] > 0.0:
            return DeviceType.GPU if row["gpu"] <= row["cpu"] else DeviceType.CPU
        return DeviceType.GPU

    def record(self, operation: OperationType, device: DeviceType, latency_ms: float) -> None:
        row = self._policy_table[operation.value]
        key = device.value
        prev = row.get(key, 0.0)
        if prev <= 0.0:
            row[key] = latency_ms
        else:
            row[key] = (prev * 0.8) + (latency_ms * 0.2)

    def get_policy_table(self) -> Dict[str, Dict[str, float]]:
        return {op: {"cpu": round(v["cpu"], 3), "gpu": round(v["gpu"], 3)} for op, v in self._policy_table.items()}


class HeterogeneousComputeEngine:
    """Execute tasks via adaptive CPU/GPU routing with offline-safe defaults."""

    def __init__(self, policy: SchedulingPolicy = SchedulingPolicy.ADAPTIVE) -> None:
        self.policy = policy
        self.caps = ComputeCapabilities(gpu_available=False, gpu_name="offline", cpu_cores=4)
        self.scheduler = AdaptiveScheduler()
        self._stats = {
            "total_tasks": 0,
            "cpu": {"tasks_completed": 0, "total_latency_ms": 0.0, "avg_latency_ms": 0.0},
            "gpu": {"tasks_completed": 0, "total_latency_ms": 0.0, "avg_latency_ms": 0.0},
        }
        self._task_log: List[Dict[str, Any]] = []

    def execute(
        self,
        operation: OperationType,
        fn: Callable[..., Any],
        *args: Any,
        **kwargs: Any,
    ) -> Dict[str, Any]:
        if not callable(fn):
            raise ValueError("fn must be callable")
        device = self.scheduler.choose(operation=operation, caps=self.caps, policy=self.policy)
        start = time.perf_counter()
        output = fn(*args, **kwargs)
        latency_ms = (time.perf_counter() - start) * 1000.0
        self.scheduler.record(operation=operation, device=device, latency_ms=latency_ms)
        self._update_stats(device, latency_ms)
        record = {
            "operation": operation.value,
            "device": device.value,
            "latency_ms": round(latency_ms, 3),
        }
        self._task_log.append(record)
        if len(self._task_log) > 2000:
            self._task_log = self._task_log[-2000:]
        return {"device": device.value, "latency_ms": round(latency_ms, 3), "result": output}

    def _update_stats(self, device: DeviceType, latency_ms: float) -> None:
        self._stats["total_tasks"] += 1
        row = self._stats[device.value]
        row["tasks_completed"] += 1
        row["total_latency_ms"] += latency_ms
        row["avg_latency_ms"] = row["total_latency_ms"] / max(1, row["tasks_completed"])

    def device_stats(self) -> Dict[str, Any]:
        return {
            "total_tasks": self._stats["total_tasks"],
            "cpu": {
                "tasks_completed": self._stats["cpu"]["tasks_completed"],
                "avg_latency_ms": round(self._stats["cpu"]["avg_latency_ms"], 3),
            },
            "gpu": {
                "tasks_completed": self._stats["gpu"]["tasks_completed"],
                "avg_latency_ms": round(self._stats["gpu"]["avg_latency_ms"], 3),
            },
        }

    def health_check(self) -> Dict[str, Any]:
        return {
            "status": "operational",
            "policy": self.policy.value,
            "capabilities": self.caps.to_dict(),
            "stats": self.device_stats(),
            "policy_table": self.scheduler.get_policy_table(),
        }
