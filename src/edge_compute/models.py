"""Data models for edge self-replication and sandbox orchestration."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, Optional


class NodeStatus(str, Enum):
    """Lifecycle status for replicated edge nodes."""

    STARTING = "starting"
    ONLINE = "online"
    OFFLINE = "offline"
    DEGRADED = "degraded"
    ERROR = "error"


@dataclass
class EdgeNodeInfo:
    """Hardware profile used to size replica models for field hardware."""

    node_id: str
    cpu_cores: int
    memory_mb: int
    disk_mb: int
    gpu_available: bool = False
    labels: Dict[str, str] = field(default_factory=dict)
    status: NodeStatus = NodeStatus.OFFLINE
    last_seen: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def __post_init__(self) -> None:
        if not isinstance(self.node_id, str) or not self.node_id.strip():
            raise ValueError("node_id must be a non-empty string")
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
        if not isinstance(self.status, NodeStatus):
            self.status = NodeStatus(str(self.status))
        if not isinstance(self.last_seen, datetime):
            raise ValueError("last_seen must be datetime")


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
