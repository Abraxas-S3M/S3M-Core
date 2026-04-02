"""Federated edge compute components for tactical offline training."""

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
]
