"""Federated and self-training edge compute components for tactical offline training."""

from src.edge_compute.federated_engine import (
    FederatedEngine,
    RDPAccountant,
    decompress_gradient,
    fedavg_aggregate,
    fedprox_local_objective,
    scaffold_correction,
    topk_compress,
)
from src.edge_compute.models import (
    AggregationStrategy,
    EdgeNodeInfo,
    FederatedRound,
    NodeStatus,
    PseudoLabelBatch,
    SelfTrainingStrategy,
)
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
    "EdgeNodeInfo",
    "FederatedRound",
    "NodeStatus",
    "FederatedEngine",
    "RDPAccountant",
    "topk_compress",
    "decompress_gradient",
    "fedavg_aggregate",
    "fedprox_local_objective",
    "scaffold_correction",
    "PseudoLabelBatch",
    "SelfTrainingStrategy",
    "NumpyLinearModel",
    "SelfTrainingEngine",
    "dropout_noise",
    "gaussian_noise",
    "mixup",
    "apply_noise_chain",
]
