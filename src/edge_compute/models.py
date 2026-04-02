"""Typed models for S3M heterogeneous CPU/GPU compute orchestration.

UNCLASSIFIED - FOUO
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from time import time
from typing import Any, Dict, Optional


class DeviceType(str, Enum):
    """Execution target for tactical compute workloads."""

    AUTO = "auto"
    CPU = "cpu"
    GPU = "gpu"

    @classmethod
    def from_value(cls, value: str | "DeviceType") -> "DeviceType":
        if isinstance(value, cls):
            return value
        if not isinstance(value, str):
            raise ValueError(f"Invalid device type: {value}")
        normalized = value.strip().lower()
        for item in cls:
            if item.value == normalized:
                return item
        raise ValueError(f"Invalid device type: {value}")


class OperationType(str, Enum):
    """Operation family to route tactical workloads per device affinity."""

    MATMUL = "matmul"
    CONV = "conv"
    ATTENTION = "attention"
    TRAINING_STEP = "training_step"
    EMBEDDING = "embedding"
    TOKENIZATION = "tokenization"
    PREPROCESSING = "preprocessing"
    POSTPROCESSING = "postprocessing"
    IO = "io"
    EVALUATION = "evaluation"
    INFERENCE = "inference"

    @classmethod
    def from_value(cls, value: str | "OperationType") -> "OperationType":
        if isinstance(value, cls):
            return value
        if not isinstance(value, str):
            raise ValueError(f"Invalid operation type: {value}")
        normalized = value.strip().lower()
        for item in cls:
            if item.value == normalized:
                return item
        raise ValueError(f"Invalid operation type: {value}")


class SchedulingPolicy(str, Enum):
    """Routing policy for CPU/GPU assignment in contested edge conditions."""

    ADAPTIVE = "adaptive"
    PREFER_GPU = "prefer_gpu"
    PREFER_CPU = "prefer_cpu"
    ROUND_ROBIN = "round_robin"

    @classmethod
    def from_value(cls, value: str | "SchedulingPolicy") -> "SchedulingPolicy":
        if isinstance(value, cls):
            return value
        if not isinstance(value, str):
            raise ValueError(f"Invalid scheduling policy: {value}")
        normalized = value.strip().lower()
        for item in cls:
            if item.value == normalized:
                return item
        raise ValueError(f"Invalid scheduling policy: {value}")


@dataclass
class ComputeTask:
    """Single routed compute task in the heterogeneous execution queue."""

    task_id: str
    operation: OperationType
    assigned_device: DeviceType = DeviceType.AUTO
    payload_size_bytes: int = 0
    metadata: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not isinstance(self.task_id, str) or not self.task_id.strip():
            raise ValueError("task_id must be a non-empty string")
        self.operation = OperationType.from_value(self.operation)
        self.assigned_device = DeviceType.from_value(self.assigned_device)
        if not isinstance(self.payload_size_bytes, int) or self.payload_size_bytes < 0:
            raise ValueError("payload_size_bytes must be a non-negative integer")
        if not isinstance(self.metadata, dict):
            raise ValueError("metadata must be a dictionary")

    def to_dict(self) -> Dict[str, Any]:
        return {
            "task_id": self.task_id,
            "operation": self.operation.value,
            "assigned_device": self.assigned_device.value,
            "payload_size_bytes": self.payload_size_bytes,
            "metadata": dict(self.metadata),
        }


@dataclass
class DeviceStats:
    """Runtime device telemetry used for tactical scheduler decisions."""

    device: DeviceType
    utilization_pct: float = 0.0
    avg_latency_ms: float = 0.0
    tasks_completed: int = 0
    failed_tasks: int = 0
    memory_used_mb: float = 0.0
    power_watts: float = 0.0

    def __post_init__(self) -> None:
        self.device = DeviceType.from_value(self.device)
        if not isinstance(self.utilization_pct, (int, float)):
            raise ValueError("utilization_pct must be numeric")
        self.utilization_pct = float(min(max(self.utilization_pct, 0.0), 100.0))
        if not isinstance(self.avg_latency_ms, (int, float)) or self.avg_latency_ms < 0:
            raise ValueError("avg_latency_ms must be non-negative")
        self.avg_latency_ms = float(self.avg_latency_ms)
        if not isinstance(self.tasks_completed, int) or self.tasks_completed < 0:
            raise ValueError("tasks_completed must be a non-negative integer")
        if not isinstance(self.failed_tasks, int) or self.failed_tasks < 0:
            raise ValueError("failed_tasks must be a non-negative integer")
        if not isinstance(self.memory_used_mb, (int, float)) or self.memory_used_mb < 0:
            raise ValueError("memory_used_mb must be non-negative")
        self.memory_used_mb = float(self.memory_used_mb)
        if not isinstance(self.power_watts, (int, float)) or self.power_watts < 0:
            raise ValueError("power_watts must be non-negative")
        self.power_watts = float(self.power_watts)

    def model_dump(self) -> Dict[str, Any]:
        return {
            "device": self.device.value,
            "utilization_pct": self.utilization_pct,
            "avg_latency_ms": self.avg_latency_ms,
            "tasks_completed": self.tasks_completed,
            "failed_tasks": self.failed_tasks,
            "memory_used_mb": self.memory_used_mb,
            "power_watts": self.power_watts,
        }


@dataclass
class SchedulerDecision:
    """Audit record for each routing decision in operational execution."""

    task_id: str
    operation: OperationType
    chosen_device: DeviceType
    actual_latency_ms: float
    reward: float
    timestamp_s: float = field(default_factory=time)
    notes: Optional[str] = None

    def __post_init__(self) -> None:
        if not isinstance(self.task_id, str):
            raise ValueError("task_id must be a string")
        self.operation = OperationType.from_value(self.operation)
        self.chosen_device = DeviceType.from_value(self.chosen_device)
        if not isinstance(self.actual_latency_ms, (int, float)) or self.actual_latency_ms < 0:
            raise ValueError("actual_latency_ms must be non-negative")
        self.actual_latency_ms = float(self.actual_latency_ms)
        if not isinstance(self.reward, (int, float)) or not (0.0 <= float(self.reward) <= 1.0):
            raise ValueError("reward must be in [0, 1]")
        self.reward = float(self.reward)
        if not isinstance(self.timestamp_s, (int, float)) or self.timestamp_s <= 0:
            raise ValueError("timestamp_s must be positive")
        self.timestamp_s = float(self.timestamp_s)
        if self.notes is not None and not isinstance(self.notes, str):
            raise ValueError("notes must be a string or None")

    def to_dict(self) -> Dict[str, Any]:
        return {
            "task_id": self.task_id,
            "operation": self.operation.value,
            "chosen_device": self.chosen_device.value,
            "actual_latency_ms": self.actual_latency_ms,
            "reward": self.reward,
            "timestamp_s": self.timestamp_s,
            "notes": self.notes,
        }
