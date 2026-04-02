"""
S3M Edge Computing & Heterogeneous Compute — Data Models
UNCLASSIFIED - FOUO

Pydantic models for federated learning, self-training, self-replication,
autonomous data generation, sandbox control, and GPU↔CPU scheduling.
"""

from __future__ import annotations

import enum
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from uuid import uuid4

from pydantic import BaseModel, Field


# ═══════════════════════════════════════════════════════════
# Enumerations
# ═══════════════════════════════════════════════════════════

class NodeStatus(str, enum.Enum):
    ONLINE = "online"
    OFFLINE = "offline"
    TRAINING = "training"
    REPLICATING = "replicating"
    DEGRADED = "degraded"


class AggregationStrategy(str, enum.Enum):
    FEDAVG = "fedavg"
    FEDPROX = "fedprox"
    SCAFFOLD = "scaffold"
    HIERARCHICAL = "hierarchical"


class SelfTrainingStrategy(str, enum.Enum):
    NOISY_STUDENT = "noisy_student"
    PSEUDO_LABEL = "pseudo_label"
    CO_TRAINING = "co_training"


class DataGenStrategy(str, enum.Enum):
    CONTRASTIVE = "contrastive_augmentation"
    GENERATIVE_REPLAY = "generative_replay"
    ACTIVE_LEARNING = "active_learning"
    ENTITY_LINKING = "entity_linking"


class DeviceType(str, enum.Enum):
    CPU = "cpu"
    GPU = "gpu"
    AUTO = "auto"


class SchedulingPolicy(str, enum.Enum):
    ADAPTIVE = "adaptive"
    PREFER_GPU = "prefer_gpu"
    PREFER_CPU = "prefer_cpu"
    ROUND_ROBIN = "round_robin"


class OperationType(str, enum.Enum):
    TOKENIZATION = "tokenization"
    PREPROCESSING = "preprocessing"
    POSTPROCESSING = "postprocessing"
    IO = "io"
    EVALUATION = "evaluation"
    MATMUL = "matmul"
    CONV = "conv"
    ATTENTION = "attention"
    TRAINING_STEP = "training_step"
    EMBEDDING = "embedding"
    CUSTOM = "custom"


# ═══════════════════════════════════════════════════════════
# Edge Network Models
# ═══════════════════════════════════════════════════════════

class EdgeNodeInfo(BaseModel):
    """Identity and capability descriptor for a single edge node."""
    node_id: str = Field(default_factory=lambda: str(uuid4()))
    hostname: str = ""
    ip_address: str = ""
    port: int = 9090
    status: NodeStatus = NodeStatus.ONLINE
    cpu_cores: int = 0
    memory_mb: int = 0
    gpu_available: bool = False
    gpu_memory_mb: int = 0
    model_version: int = 0
    last_heartbeat: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    metadata: Dict[str, Any] = Field(default_factory=dict)


class FederatedRound(BaseModel):
    """Metadata for a single federated learning aggregation round."""
    round_id: int
    participating_nodes: List[str]
    strategy: AggregationStrategy
    global_loss: float = 0.0
    avg_local_loss: float = 0.0
    gradients_compressed: bool = False
    dp_applied: bool = False
    started_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    completed_at: Optional[datetime] = None
    duration_seconds: float = 0.0


class PseudoLabelBatch(BaseModel):
    """A batch of pseudo-labeled samples from self-training."""
    batch_id: str = Field(default_factory=lambda: str(uuid4()))
    strategy: SelfTrainingStrategy
    sample_count: int
    avg_confidence: float
    noise_applied: bool = False
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class ReplicaSpec(BaseModel):
    """Specification for a self-replicated edge node."""
    replica_id: str = Field(default_factory=lambda: str(uuid4()))
    parent_node_id: str
    container_id: str = ""
    distillation_ratio: float = 0.6
    status: NodeStatus = NodeStatus.OFFLINE
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    resource_limits: Dict[str, int] = Field(default_factory=dict)


class GeneratedDataset(BaseModel):
    """Metadata for an autonomously generated dataset."""
    dataset_id: str = Field(default_factory=lambda: str(uuid4()))
    strategy: DataGenStrategy
    record_count: int = 0
    file_path: str = ""
    file_size_bytes: int = 0
    schema: Dict[str, str] = Field(default_factory=dict)
    knowledge_graph_entities: int = 0
    knowledge_graph_edges: int = 0
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class SandboxState(BaseModel):
    """Runtime state of a sandboxed engine deployment."""
    sandbox_id: str = Field(default_factory=lambda: str(uuid4()))
    container_id: str = ""
    running: bool = False
    parameters: Dict[str, Any] = Field(default_factory=dict)
    uptime_seconds: float = 0.0
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


# ═══════════════════════════════════════════════════════════
# Heterogeneous Compute Models
# ═══════════════════════════════════════════════════════════

class ComputeTask(BaseModel):
    """A unit of work to be scheduled across CPU/GPU."""
    task_id: str = Field(default_factory=lambda: str(uuid4()))
    operation: OperationType
    payload_size_bytes: int = 0
    assigned_device: DeviceType = DeviceType.AUTO
    priority: int = 5  # 1=highest, 10=lowest
    metadata: Dict[str, Any] = Field(default_factory=dict)


class DeviceStats(BaseModel):
    """Runtime performance statistics for a compute device."""
    device: DeviceType
    utilization_pct: float = 0.0
    memory_used_mb: float = 0.0
    memory_total_mb: float = 0.0
    avg_latency_ms: float = 0.0
    tasks_completed: int = 0
    power_draw_watts: float = 0.0


class SchedulerDecision(BaseModel):
    """Record of a scheduling decision made by the adaptive scheduler."""
    task_id: str
    operation: OperationType
    chosen_device: DeviceType
    predicted_latency_ms: float = 0.0
    actual_latency_ms: float = 0.0
    reward: float = 0.0
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class OffloadRequest(BaseModel):
    """Request to offload computation to a remote node."""
    request_id: str = Field(default_factory=lambda: str(uuid4()))
    source_device: DeviceType
    target_device: DeviceType
    operation: OperationType
    payload_size_bytes: int = 0
    timeout_seconds: float = 30.0
