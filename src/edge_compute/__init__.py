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
from src.edge_compute.data_value_assessor import DataValueEngine
from src.edge_compute.governed_replication import (
    CLASSIFICATION_LEVELS,
    GovernedReplicationEngine,
    ReplicationPolicy,
    ReplicationToken,
)
from src.edge_compute.manager import EdgeComputeManager
from src.edge_compute.models import (
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
from src.edge_compute.self_growth import GrowableModel, PlateauDetector, SelfGrowthEngine
from src.edge_compute.self_training import (
    NumpyLinearModel,
    SelfTrainingEngine,
    apply_noise_chain,
    dropout_noise,
    gaussian_noise,
    mixup,
)

__all__ = [
    "AggregationStrategy",
    "AdaptiveScheduler",
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
    "apply_noise_chain",
    "PlateauDetector",
    "GrowableModel",
    "SelfGrowthEngine",
    "CLASSIFICATION_LEVELS",
    "ReplicationToken",
    "ReplicationPolicy",
    "GovernedReplicationEngine",
    "DataValueEngine",
    "EdgeComputeManager",
]
