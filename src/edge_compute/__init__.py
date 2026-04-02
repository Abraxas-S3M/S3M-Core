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
    ReplicaSpec,
    SandboxState,
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
]
