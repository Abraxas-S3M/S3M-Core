"""Data models for tactical edge learning on CPU nodes.

Combines contracts for:
  - Federated training coordination across disconnected edge nodes.
  - Local self-training loops (Noisy Student, Pseudo-Label, Co-Training).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List


class AggregationStrategy(str, Enum):
    """Federated aggregation strategy used for tactical training rounds."""

    FEDAVG = "fedavg"
    FEDPROX = "fedprox"
    SCAFFOLD = "scaffold"
    HIERARCHICAL = "hierarchical"


class NodeStatus(str, Enum):
    """Operational state of an edge node in the federated mesh."""

    ONLINE = "online"
    TRAINING = "training"
    OFFLINE = "offline"
    DEGRADED = "degraded"
    LOST = "lost"


@dataclass
class EdgeNodeInfo:
    """Validated identity and health metadata for a tactical edge node."""

    node_id: str
    hostname: str
    status: NodeStatus = NodeStatus.ONLINE
    cpu_cores: int = 1
    memory_mb: int = 512
    last_heartbeat: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

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
