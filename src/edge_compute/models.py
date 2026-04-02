"""Data models for tactical edge learning and autonomous generation."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional


class DataGenStrategy(str, Enum):
    """Strategy identifier for autonomous data generation outputs."""

    CONTRASTIVE = "contrastive"
    GENERATIVE_REPLAY = "generative_replay"
    ACTIVE_LEARNING = "active_learning"
    AUTO_ENTITY_LINKING = "auto_entity_linking"

class AggregationStrategy(str, Enum):
    """Federated aggregation strategy used for tactical training rounds."""

    FEDAVG = "fedavg"
    FEDPROX = "fedprox"
    SCAFFOLD = "scaffold"
    HIERARCHICAL = "hierarchical"


class NodeStatus(str, Enum):
    """Operational state of an edge node in the federated mesh."""

    STARTING = "starting"
    ONLINE = "online"
    TRAINING = "training"
    OFFLINE = "offline"
    DEGRADED = "degraded"
    LOST = "lost"
    ERROR = "error"


@dataclass
class EdgeNodeInfo:
    """Validated identity and hardware profile for a tactical edge node."""

    node_id: str
    hostname: str = "unknown"
    status: NodeStatus = NodeStatus.ONLINE
    cpu_cores: int = 1
    memory_mb: int = 512
    disk_mb: int = 1024
    gpu_available: bool = False
    labels: Dict[str, str] = field(default_factory=dict)
    last_heartbeat: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    last_seen: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def __post_init__(self) -> None:
        if not isinstance(self.node_id, str) or not self.node_id.strip():
            raise ValueError("node_id must be a non-empty string")
        if not isinstance(self.hostname, str) or not self.hostname.strip():
            raise ValueError("hostname must be a non-empty string")
        if not isinstance(self.status, NodeStatus):
            self.status = NodeStatus(str(self.status))
        if not isinstance(self.cpu_cores, int) or self.cpu_cores <= 0:
            raise ValueError("cpu_cores must be a positive integer")
        if not isinstance(self.memory_mb, int) or self.memory_mb <= 0:
            raise ValueError("memory_mb must be a positive integer")
        if not isinstance(self.disk_mb, int) or self.disk_mb <= 0:
            raise ValueError("disk_mb must be a positive integer")
        if not isinstance(self.gpu_available, bool):
            raise ValueError("gpu_available must be bool")
        if not isinstance(self.labels, dict):
            raise ValueError("labels must be a dict")
        if not isinstance(self.last_heartbeat, datetime):
            raise ValueError("last_heartbeat must be datetime")
        if not isinstance(self.last_seen, datetime):
            raise ValueError("last_seen must be datetime")

    def to_dict(self) -> Dict[str, Any]:
        return {
            "node_id": self.node_id,
            "hostname": self.hostname,
            "status": self.status.value,
            "cpu_cores": self.cpu_cores,
            "memory_mb": self.memory_mb,
            "disk_mb": self.disk_mb,
            "gpu_available": self.gpu_available,
            "labels": dict(self.labels),
            "last_heartbeat": self.last_heartbeat.isoformat(),
            "last_seen": self.last_seen.isoformat(),
        }


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
            self.strategy = AggregationStrategy(str(self.strategy))
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


@dataclass
class ReplicaSpec:
    """Deployment contract for one autonomous replica instance."""

    replica_id: str
    parent_node_id: str
    container_id: str
    distillation_ratio: float
    status: NodeStatus
    resource_limits: Dict[str, int]
    model_snapshot_path: str = ""
    quantization: str = "int8"
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    metadata: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not isinstance(self.replica_id, str) or not self.replica_id.strip():
            raise ValueError("replica_id must be a non-empty string")
        if not isinstance(self.parent_node_id, str) or not self.parent_node_id.strip():
            raise ValueError("parent_node_id must be a non-empty string")
        if not isinstance(self.container_id, str):
            raise ValueError("container_id must be a string")
        if not isinstance(self.distillation_ratio, (int, float)):
            raise ValueError("distillation_ratio must be numeric")
        ratio = float(self.distillation_ratio)
        if ratio <= 0.0 or ratio > 1.0:
            raise ValueError("distillation_ratio must be in (0, 1]")
        self.distillation_ratio = ratio
        if not isinstance(self.status, NodeStatus):
            self.status = NodeStatus(str(self.status))
        if not isinstance(self.resource_limits, dict):
            raise ValueError("resource_limits must be a dict")
        if not isinstance(self.quantization, str) or not self.quantization.strip():
            raise ValueError("quantization must be a non-empty string")
        if not isinstance(self.created_at, datetime):
            raise ValueError("created_at must be datetime")
        if not isinstance(self.metadata, dict):
            raise ValueError("metadata must be a dict")


@dataclass
class SandboxState:
    """Tracks isolated runtime sandboxes used for tactical experimentation."""

    sandbox_id: str
    container_id: str
    running: bool
    parameters: Dict[str, Any]
    config_path: str = ""
    last_reconfigured: Optional[datetime] = None
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def __post_init__(self) -> None:
        if not isinstance(self.sandbox_id, str) or not self.sandbox_id.strip():
            raise ValueError("sandbox_id must be a non-empty string")
        if not isinstance(self.container_id, str):
            raise ValueError("container_id must be a string")
        if not isinstance(self.running, bool):
            raise ValueError("running must be bool")
        if not isinstance(self.parameters, dict):
            raise ValueError("parameters must be a dict")
        if not isinstance(self.config_path, str):
            raise ValueError("config_path must be a string")
        if self.last_reconfigured is not None and not isinstance(self.last_reconfigured, datetime):
            raise ValueError("last_reconfigured must be datetime or None")
        if not isinstance(self.created_at, datetime):
            raise ValueError("created_at must be datetime")


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
