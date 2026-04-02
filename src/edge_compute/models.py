"""Unified data models for tactical edge compute operations.

UNCLASSIFIED - FOUO
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from time import time
from typing import Any, Dict, List, Optional
from uuid import uuid4


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
    CUSTOM = "custom"

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


class DataGenStrategy(str, Enum):
    """Strategy identifier for autonomous data generation outputs."""

    CONTRASTIVE = "contrastive"
    GENERATIVE_REPLAY = "generative_replay"
    ACTIVE_LEARNING = "active_learning"
    AUTO_ENTITY_LINKING = "auto_entity_linking"


@dataclass
class GeneratedDataset:
    """Metadata for a generated dataset artifact written to local disk."""

    strategy: DataGenStrategy
    record_count: int
    file_path: str
    file_size_bytes: int
    schema: Dict[str, Any]

    def __post_init__(self) -> None:
        if not isinstance(self.strategy, DataGenStrategy):
            self.strategy = DataGenStrategy(str(self.strategy))
        if not isinstance(self.record_count, int) or self.record_count < 0:
            raise ValueError("record_count must be a non-negative integer")
        if not isinstance(self.file_path, str) or not self.file_path.strip():
            raise ValueError("file_path must be a non-empty string")
        if not isinstance(self.file_size_bytes, int) or self.file_size_bytes < 0:
            raise ValueError("file_size_bytes must be a non-negative integer")
        if not isinstance(self.schema, dict):
            raise ValueError("schema must be a dictionary")

    def to_dict(self) -> Dict[str, Any]:
        return {
            "strategy": self.strategy.value,
            "record_count": self.record_count,
            "file_path": self.file_path,
            "file_size_bytes": self.file_size_bytes,
            "schema": dict(self.schema),
        }


@dataclass
class EdgeNodeInfo:
    """Validated identity and health metadata for a tactical edge node."""

    hostname: str
    node_id: str = field(default_factory=lambda: str(uuid4()))
    status: "NodeStatus" = field(default="online")
    cpu_cores: int = 1
    memory_mb: int = 512
    last_heartbeat: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def __post_init__(self) -> None:
        if not isinstance(self.node_id, str) or not self.node_id.strip():
            raise ValueError("node_id must be a non-empty string")
        if not isinstance(self.hostname, str) or not self.hostname.strip():
            raise ValueError("hostname must be a non-empty string")
        if not isinstance(self.status, NodeStatus):
            self.status = NodeStatus(str(self.status).lower())
        if not isinstance(self.cpu_cores, int) or self.cpu_cores <= 0:
            raise ValueError("cpu_cores must be a positive integer")
        if not isinstance(self.memory_mb, int) or self.memory_mb <= 0:
            raise ValueError("memory_mb must be a positive integer")
        if not isinstance(self.last_heartbeat, datetime):
            raise ValueError("last_heartbeat must be a datetime")

    def to_dict(self) -> Dict[str, Any]:
        return {
            "node_id": self.node_id,
            "hostname": self.hostname,
            "status": self.status.value,
            "cpu_cores": self.cpu_cores,
            "memory_mb": self.memory_mb,
            "last_heartbeat": self.last_heartbeat.isoformat(),
        }


class NodeStatus(str, Enum):
    """Operational state of an edge node in the federated mesh."""

    ONLINE = "online"
    TRAINING = "training"
    OFFLINE = "offline"
    DEGRADED = "degraded"
    LOST = "lost"


class AggregationStrategy(str, Enum):
    """Federated aggregation strategy used for tactical training rounds."""

    FEDAVG = "fedavg"
    FEDPROX = "fedprox"
    SCAFFOLD = "scaffold"
    HIERARCHICAL = "hierarchical"


@dataclass
class FederatedRound:
    """Auditable record of one tactical federated aggregation cycle."""

    round_id: int
    participating_nodes: List[str]
    strategy: AggregationStrategy
    global_loss: float = 0.0
    gradients_compressed: bool = False
    dp_applied: bool = False
    duration_seconds: float = 0.0
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def __post_init__(self) -> None:
        if not isinstance(self.round_id, int) or self.round_id < 0:
            raise ValueError("round_id must be a non-negative integer")
        if not isinstance(self.participating_nodes, list):
            raise ValueError("participating_nodes must be a list")
        if any(not isinstance(node_id, str) or not node_id for node_id in self.participating_nodes):
            raise ValueError("participating_nodes entries must be non-empty strings")
        if not isinstance(self.strategy, AggregationStrategy):
            self.strategy = AggregationStrategy(str(self.strategy).lower())
        if not isinstance(self.global_loss, (int, float)):
            raise ValueError("global_loss must be numeric")
        self.global_loss = float(self.global_loss)
        if not isinstance(self.gradients_compressed, bool):
            raise ValueError("gradients_compressed must be bool")
        if not isinstance(self.dp_applied, bool):
            raise ValueError("dp_applied must be bool")
        if not isinstance(self.duration_seconds, (int, float)) or float(self.duration_seconds) < 0.0:
            raise ValueError("duration_seconds must be a non-negative number")
        self.duration_seconds = float(self.duration_seconds)
        if not isinstance(self.created_at, datetime):
            raise ValueError("created_at must be a datetime")

    def to_dict(self) -> Dict[str, Any]:
        return {
            "round_id": self.round_id,
            "participating_nodes": list(self.participating_nodes),
            "strategy": self.strategy.value,
            "global_loss": self.global_loss,
            "gradients_compressed": self.gradients_compressed,
            "dp_applied": self.dp_applied,
            "duration_seconds": self.duration_seconds,
            "created_at": self.created_at.isoformat(),
        }


class SelfTrainingStrategy(str, Enum):
    """Supported self-training strategies for edge adaptation."""

    NOISY_STUDENT = "noisy_student"
    PSEUDO_LABEL = "pseudo_label"
    CO_TRAINING = "co_training"


@dataclass
class PseudoLabelBatch:
    """Summary of pseudo-label output for one self-training cycle."""

    strategy: SelfTrainingStrategy
    sample_count: int
    avg_confidence: float
    noise_applied: bool = False

    def __post_init__(self) -> None:
        if not isinstance(self.strategy, SelfTrainingStrategy):
            self.strategy = SelfTrainingStrategy(str(self.strategy).lower())
        if not isinstance(self.sample_count, int) or self.sample_count < 0:
            raise ValueError("sample_count must be a non-negative integer")
        if not isinstance(self.avg_confidence, (int, float)) or not (0.0 <= float(self.avg_confidence) <= 1.0):
            raise ValueError("avg_confidence must be in [0, 1]")
        self.avg_confidence = float(self.avg_confidence)
        if not isinstance(self.noise_applied, bool):
            raise ValueError("noise_applied must be bool")

    def to_dict(self) -> Dict[str, Any]:
        return {
            "strategy": self.strategy.value,
            "sample_count": self.sample_count,
            "avg_confidence": self.avg_confidence,
            "noise_applied": self.noise_applied,
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
