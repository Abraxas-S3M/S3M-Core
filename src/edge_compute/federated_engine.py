"""Federated learning engine with secure tactical-safe defaults."""

from __future__ import annotations

import logging
from typing import Dict, List

import numpy as np

from src.edge_compute.models import (
    AggregationStrategy,
    EdgeNodeInfo,
    FederatedRound,
    NodeStatus,
)

logger = logging.getLogger("s3m.edge.federated")


class FederatedEngine:
    """Manage federated roster, rounds, and privacy budget in-process."""

    def __init__(
        self,
        strategy: AggregationStrategy = AggregationStrategy.FEDPROX,
        dp_epsilon: float = 8.0,
        compression_sparsity: float = 0.9,
    ) -> None:
        self.strategy = strategy
        self.dp_epsilon = float(max(0.1, dp_epsilon))
        self.compression_sparsity = float(min(max(compression_sparsity, 0.0), 0.99))
        self._nodes: Dict[str, EdgeNodeInfo] = {}
        self._round_counter = 0
        self._rounds: List[FederatedRound] = []
        self._epsilon_spent = 0.0
        self._global_params: Dict[str, np.ndarray] = {}

    def register_node(self, node: EdgeNodeInfo) -> None:
        self._nodes[node.node_id] = node
        logger.info("Registered edge node for federation: %s", node.node_id)

    def deregister_node(self, node_id: str) -> bool:
        return self._nodes.pop(node_id, None) is not None

    def active_nodes(self) -> List[EdgeNodeInfo]:
        return [n for n in self._nodes.values() if n.status != NodeStatus.OFFLINE]

    def initialize_global_model(self, params: Dict[str, np.ndarray]) -> None:
        self._global_params = dict(params)

    def get_global_params(self) -> Dict[str, np.ndarray]:
        return dict(self._global_params)

    def record_round(self, participating_nodes: List[str], duration_seconds: float) -> FederatedRound:
        self._round_counter += 1
        delta = min(0.1, self.dp_epsilon * 0.01)
        self._epsilon_spent = min(self.dp_epsilon, self._epsilon_spent + delta)
        payload = FederatedRound(
            round_id=self._round_counter,
            participating_nodes=list(participating_nodes),
            duration_seconds=max(0.0, float(duration_seconds)),
            gradients_compressed=self.compression_sparsity > 0.0,
            aggregation_strategy=self.strategy,
        )
        self._rounds.append(payload)
        return payload

    def round_history(self) -> List[FederatedRound]:
        return list(self._rounds)

    def dp_status(self) -> Dict[str, float | bool]:
        remaining = max(0.0, self.dp_epsilon - self._epsilon_spent)
        return {
            "epsilon_budget": self.dp_epsilon,
            "epsilon_spent": self._epsilon_spent,
            "epsilon_remaining": remaining,
            "budget_exhausted": remaining <= 1e-9,
        }

    def health_check(self) -> Dict[str, object]:
        dp = self.dp_status()
        return {
            "status": "operational",
            "strategy": self.strategy.value,
            "registered_nodes": len(self._nodes),
            "active_nodes": len(self.active_nodes()),
            "rounds_completed": self._round_counter,
            "dp": dp,
        }
