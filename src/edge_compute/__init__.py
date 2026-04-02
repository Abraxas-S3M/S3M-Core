"""
S3M Edge Computing & Heterogeneous Compute Layer
UNCLASSIFIED - FOUO

Two novel subsystems:
  1. Edge CPU Network — Federated self-training, self-replication, autonomous
     data generation, and sandboxed deployment on CPU-only edge devices.
  2. Heterogeneous Compute — Adaptive GPU↔CPU task scheduling with RL-based
     device assignment, unified memory, and remote offload bridge.

Integrates with:
  - Layer 01 (LLM Core) for model weights and inference
  - Layer 02 (Threat Detection) for edge anomaly detection
  - Layer 04 (Simulation) for synthetic data pipelines
  - Layer 05 (Navigation) for edge inference engine
  - Layer 06 (Dashboard) for monitoring
"""

from src.edge_compute.data_generation import (
    ActiveLearner,
    ContrastiveAugmentor,
    DataGenerationEngine,
    GenerativeReplay,
    KnowledgeGraphBuilder,
)
from src.edge_compute.federated_engine import (
    FederatedEngine,
    RDPAccountant,
    decompress_gradient,
    fedavg_aggregate,
    fedprox_local_objective,
    scaffold_correction,
    topk_compress,
)
from src.edge_compute.governed_replication import (
    CLASSIFICATION_LEVELS,
    GovernedReplicationEngine,
    ReplicationPolicy,
    ReplicationToken,
)
from src.edge_compute.hetero_compute import (
    AdaptiveScheduler,
    DeviceCapabilities,
    HeterogeneousComputeEngine,
    MemoryManager,
)
from src.edge_compute.models import (
    AggregationStrategy,
    ComputeTask,
    DataGenStrategy,
    DeviceStats,
    DeviceType,
    EdgeNodeInfo,
    FederatedRound,
    GeneratedDataset,
    NodeStatus,
    OffloadRequest,
    OperationType,
    PseudoLabelBatch,
    ReplicaSpec,
    SandboxState,
    SchedulerDecision,
    SchedulingPolicy,
    SelfTrainingStrategy,
)
from src.edge_compute.sandbox_controller import SandboxController
from src.edge_compute.self_replication import ReplicationEngine
from src.edge_compute.self_training import (
    NumpyLinearModel,
    SelfTrainingEngine,
    apply_noise_chain,
    dropout_noise,
    gaussian_noise,
    mixup,
)

__all__ = [
    # Enums
    "AggregationStrategy",
    "DataGenStrategy",
    "DeviceType",
    "NodeStatus",
    "OperationType",
    "SchedulingPolicy",
    "SelfTrainingStrategy",
    # Edge Network
    "EdgeNodeInfo",
    "FederatedRound",
    "PseudoLabelBatch",
    "ReplicaSpec",
    "GeneratedDataset",
    "SandboxState",
    # Heterogeneous Compute
    "ComputeTask",
    "DeviceStats",
    "SchedulerDecision",
    "OffloadRequest",
    # Federated Engine
    "FederatedEngine",
    "RDPAccountant",
    "topk_compress",
    "decompress_gradient",
    "fedavg_aggregate",
    "fedprox_local_objective",
    "scaffold_correction",
    # Self Training
    "NumpyLinearModel",
    "SelfTrainingEngine",
    "dropout_noise",
    "gaussian_noise",
    "mixup",
    "apply_noise_chain",
    # Governed Replication
    "CLASSIFICATION_LEVELS",
    "ReplicationToken",
    "ReplicationPolicy",
    "GovernedReplicationEngine",
    # Data Generation
    "ContrastiveAugmentor",
    "GenerativeReplay",
    "KnowledgeGraphBuilder",
    "ActiveLearner",
    "DataGenerationEngine",
    # Heterogeneous Compute Engine
    "DeviceCapabilities",
    "MemoryManager",
    "AdaptiveScheduler",
    "HeterogeneousComputeEngine",
    # Runtime Sandbox / Replication
    "SandboxController",
    "ReplicationEngine",
]
