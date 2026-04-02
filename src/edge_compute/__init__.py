"""Federated, self-training, replication, and data-generation edge components."""

from .data_generation import (
    ActiveLearner,
    ContrastiveAugmentor,
    DataGenerationEngine,
    GenerativeReplay,
    KnowledgeGraphBuilder,
)
from .federated_engine import (
    FederatedEngine,
    RDPAccountant,
    decompress_gradient,
    fedavg_aggregate,
    fedprox_local_objective,
    scaffold_correction,
    topk_compress,
)
from .governed_replication import (
    CLASSIFICATION_LEVELS,
    GovernedReplicationEngine,
    ReplicationPolicy,
    ReplicationToken,
)
from .models import (
    AggregationStrategy,
    DataGenStrategy,
    EdgeNodeInfo,
    FederatedRound,
    GeneratedDataset,
    NodeStatus,
    PseudoLabelBatch,
    ReplicaSpec,
    SandboxState,
    SelfTrainingStrategy,
)
from .sandbox_controller import SandboxController
from .self_replication import ReplicationEngine
from .self_training import (
    NumpyLinearModel,
    SelfTrainingEngine,
    apply_noise_chain,
    dropout_noise,
    gaussian_noise,
    mixup,
)

__all__ = [
    "ActiveLearner",
    "AggregationStrategy",
    "CLASSIFICATION_LEVELS",
    "ContrastiveAugmentor",
    "DataGenStrategy",
    "DataGenerationEngine",
    "EdgeNodeInfo",
    "FederatedEngine",
    "FederatedRound",
    "GeneratedDataset",
    "GenerativeReplay",
    "GovernedReplicationEngine",
    "KnowledgeGraphBuilder",
    "NodeStatus",
    "NumpyLinearModel",
    "PseudoLabelBatch",
    "RDPAccountant",
    "ReplicaSpec",
    "ReplicationEngine",
    "ReplicationPolicy",
    "ReplicationToken",
    "SandboxController",
    "SandboxState",
    "SelfTrainingEngine",
    "SelfTrainingStrategy",
    "apply_noise_chain",
    "decompress_gradient",
    "dropout_noise",
    "fedavg_aggregate",
    "fedprox_local_objective",
    "gaussian_noise",
    "mixup",
    "scaffold_correction",
    "topk_compress",
]
