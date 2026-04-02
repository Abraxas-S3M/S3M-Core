"""Edge compute models and enums for tactical orchestration."""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class AggregationStrategy(str, Enum):
    FEDAVG = "fedavg"
    FEDPROX = "fedprox"
    SCAFFOLD = "scaffold"


class SelfTrainingStrategy(str, Enum):
    NOISY_STUDENT = "noisy_student"
    SELF_PACED = "self_paced"
    PSEUDO_LABEL = "pseudo_label"


class SchedulingPolicy(str, Enum):
    ADAPTIVE = "adaptive"
    GPU_PREFERRED = "gpu_preferred"
    CPU_ONLY = "cpu_only"


class OperationType(str, Enum):
    MATMUL = "matmul"
    INFERENCE = "inference"
    DATA_PREP = "data_prep"
    FEATURE_EXTRACTION = "feature_extraction"


class DeviceType(str, Enum):
    CPU = "cpu"
    GPU = "gpu"


class NodeStatus(str, Enum):
    ONLINE = "online"
    OFFLINE = "offline"
    DEGRADED = "degraded"


class ReplicaStatus(str, Enum):
    ONLINE = "online"
    OFFLINE = "offline"
    STOPPED = "stopped"


class DatasetStrategy(str, Enum):
    CONTRASTIVE = "contrastive"
    REPLAY = "replay"
    SYNTHETIC = "synthetic"


class EdgeNodeInfo(BaseModel):
    node_id: str
    hostname: str = ""
    ip_address: str = ""
    port: int = 9090
    cpu_cores: int = 0
    memory_mb: int = 0
    gpu_available: bool = False
    status: NodeStatus = NodeStatus.ONLINE


class FederatedRound(BaseModel):
    round_id: int
    participating_nodes: List[str] = Field(default_factory=list)
    duration_seconds: float = 0.0
    gradients_compressed: bool = True
    aggregation_strategy: AggregationStrategy = AggregationStrategy.FEDPROX
    timestamp: str = Field(default_factory=utc_now_iso)


class SelfTrainingBatch(BaseModel):
    cycle_id: int
    sample_count: int = 0
    avg_confidence: float = 0.0
    noise_applied: bool = False
    timestamp: str = Field(default_factory=utc_now_iso)


class ReplicaSpec(BaseModel):
    replica_id: str
    parent_node_id: str
    status: ReplicaStatus = ReplicaStatus.ONLINE
    target_memory_mb: int
    distillation_ratio: float
    container_id: Optional[str] = None
    created_at: str = Field(default_factory=utc_now_iso)


class GeneratedDataset(BaseModel):
    dataset_id: str
    strategy: DatasetStrategy
    record_count: int
    file_path: str
    file_size_bytes: int
    created_at: str = Field(default_factory=utc_now_iso)


class SandboxState(BaseModel):
    sandbox_id: str
    running: bool = True
    cpu_cores: int = 2
    memory_mb: int = 2048
    gpu_passthrough: bool = False
    network_isolation: bool = True
    parameters: Dict[str, Any] = Field(default_factory=dict)
    created_at: str = Field(default_factory=utc_now_iso)
