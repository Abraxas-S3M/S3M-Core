"""Federated and orchestration components for tactical edge compute."""

from .federated_engine import (
    FederatedEngine,
    RDPAccountant,
    decompress_gradient,
    fedavg_aggregate,
    fedprox_local_objective,
    scaffold_correction,
    topk_compress,
)
from .models import (
    AggregationStrategy,
    EdgeNodeInfo,
    FederatedRound,
    NodeStatus,
    PseudoLabelBatch,
    SelfTrainingStrategy,
    ReplicaSpec,
    SandboxState,
)
from .self_training import (
    NumpyLinearModel,
    SelfTrainingEngine,
    apply_noise_chain,
    dropout_noise,
    gaussian_noise,
    mixup,
)
from .governed_replication import (
    CLASSIFICATION_LEVELS,
    GovernedReplicationEngine,
    ReplicationPolicy,
    ReplicationToken,
)
from .sandbox_controller import SandboxController
from .self_replication import ReplicationEngine

__all__ = [
    "AggregationStrategy",
    "EdgeNodeInfo",
    "FederatedRound",
    "NodeStatus",
    "ReplicaSpec",
    "SandboxState",
    "FederatedEngine",
    "RDPAccountant",
    "topk_compress",
    "decompress_gradient",
    "fedavg_aggregate",
    "fedprox_local_objective",
    "scaffold_correction",
    "ReplicationEngine",
    "SandboxController",
    "PseudoLabelBatch",
    "SelfTrainingStrategy",
    "NumpyLinearModel",
    "SelfTrainingEngine",
    "dropout_noise",
    "gaussian_noise",
    "mixup",
    "apply_noise_chain",
    "CLASSIFICATION_LEVELS",
    "ReplicationToken",
    "ReplicationPolicy",
    "GovernedReplicationEngine",
]
