"""
S3M Edge Compute Manager
UNCLASSIFIED - FOUO

Unified orchestrator for both novel features:
  Feature 1: Edge CPU Network (federated, self-training, replication, data gen, sandbox)
  Feature 2: Heterogeneous Compute (adaptive GPU↔CPU scheduling)

This manager is the single import point for the API layer and dashboard.
"""

from __future__ import annotations

import logging
from typing import Any, Dict

import numpy as np

from src.edge_compute.data_generation import DataGenerationEngine
from src.edge_compute.federated_engine import FederatedEngine
from src.edge_compute.hetero_compute import HeterogeneousComputeEngine
from src.edge_compute.models import (
    AggregationStrategy,
    EdgeNodeInfo,
    SchedulingPolicy,
    SelfTrainingStrategy,
)
from src.edge_compute.sandbox_controller import SandboxController
from src.edge_compute.self_replication import ReplicationEngine
from src.edge_compute.self_training import NumpyLinearModel, SelfTrainingEngine

logger = logging.getLogger("s3m.edge.manager")


class EdgeComputeManager:
    """
    Top-level manager that wires together all edge compute subsystems.

    Usage:
        manager = EdgeComputeManager()
        manager.federated.register_node(node)
        manager.self_trainer.train_cycle(labeled_x, labeled_y, unlabeled_x)
        manager.replication.create_replica(parent_id, parent_params)
        manager.data_gen.generate_contrastive_dataset(data)
        sandbox = manager.sandbox.deploy()
        manager.sandbox.update_params(sandbox.sandbox_id, {"temperature": 0.5})
        result = manager.compute.execute(OperationType.MATMUL, my_fn, data)
    """

    def __init__(
        self,
        aggregation_strategy: AggregationStrategy = AggregationStrategy.FEDPROX,
        dp_epsilon: float = 8.0,
        compression_sparsity: float = 0.9,
        self_training_strategy: SelfTrainingStrategy = SelfTrainingStrategy.NOISY_STUDENT,
        confidence_threshold: float = 0.85,
        max_replicas: int = 8,
        container_runtime: str = "docker",
        data_output_dir: str = "data/edge/generated/",
        kg_db_path: str = "data/edge/knowledge.db",
        sandbox_base_image: str = "s3m-sandbox:latest",
        scheduling_policy: SchedulingPolicy | str = SchedulingPolicy.ADAPTIVE,
    ) -> None:
        resolved_policy = scheduling_policy
        if isinstance(scheduling_policy, str):
            try:
                resolved_policy = SchedulingPolicy(scheduling_policy.strip().lower())
            except Exception:
                resolved_policy = SchedulingPolicy.ADAPTIVE

        self.federated = FederatedEngine(
            strategy=aggregation_strategy,
            dp_epsilon=dp_epsilon,
            compression_sparsity=compression_sparsity,
        )
        self.self_trainer = SelfTrainingEngine(
            strategy=self_training_strategy,
            confidence_threshold=confidence_threshold,
        )
        self.replication = ReplicationEngine(
            max_replicas=max_replicas,
            container_runtime=container_runtime,
        )
        self.data_gen = DataGenerationEngine(
            output_dir=data_output_dir,
            kg_db_path=kg_db_path,
        )
        self.sandbox = SandboxController(
            runtime=container_runtime,
            base_image=sandbox_base_image,
        )
        self.compute = HeterogeneousComputeEngine(policy=resolved_policy)

        logger.info(
            "EdgeComputeManager initialized: fed=%s, train=%s, sched=%s",
            aggregation_strategy.value,
            self_training_strategy.value,
            resolved_policy.value,
        )

    def quick_self_train(
        self,
        input_dim: int,
        output_dim: int,
        labeled_x: np.ndarray,
        labeled_y: np.ndarray,
        unlabeled_x: np.ndarray,
        cycles: int = 5,
        epochs_per_cycle: int = 3,
    ) -> Dict[str, Any]:
        """
        End-to-end self-training pipeline:
          1. Initialize a small CPU model.
          2. Run N self-training cycles.
          3. Return trained model params + history.
        """
        model = NumpyLinearModel(input_dim, hidden_dim=128, output_dim=output_dim)
        self.self_trainer.initialize(model)

        for i in range(cycles):
            batch = self.self_trainer.train_cycle(
                labeled_x,
                labeled_y,
                unlabeled_x,
                epochs=epochs_per_cycle,
            )
            logger.info(
                "Quick self-train cycle %d/%d: %d pseudo-labels",
                i + 1,
                cycles,
                batch.sample_count,
            )

        student = self.self_trainer.get_student()
        params: Dict[str, Any] = {}
        if student is not None:
            # Keep API payload JSON-safe for dashboard and route consumers.
            params = {k: v.tolist() for k, v in student.params.items()}
        return {
            "model_params": params,
            "history": [b.model_dump() for b in self.self_trainer.history()],
            "cycles_completed": cycles,
        }

    def bootstrap_edge_node(
        self,
        parent_params: Dict[str, np.ndarray],
        parent_node_id: str,
        target_memory_mb: int = 4096,
        deploy_sandbox: bool = True,
    ) -> Dict[str, Any]:
        """
        Full bootstrap sequence for a new edge node:
          1. Create a self-replica with distilled model.
          2. Deploy a sandbox with default parameters.
          3. Initialize federated registration.
        """
        replica = self.replication.create_replica(
            parent_node_id=parent_node_id,
            parent_params=parent_params,
            target_memory_mb=target_memory_mb,
        )

        sandbox_state = None
        if deploy_sandbox:
            sandbox_state = self.sandbox.deploy(
                memory_mb=min(2048, target_memory_mb // 2),
                env_vars={"S3M_NODE_ID": replica.replica_id},
            )

        node_info = EdgeNodeInfo(
            node_id=replica.replica_id,
            memory_mb=target_memory_mb,
            status=replica.status.value,
        )
        self.federated.register_node(node_info)

        return {
            "replica": replica.model_dump(),
            "sandbox": sandbox_state.model_dump() if sandbox_state else None,
            "node_info": node_info.model_dump(),
        }

    def health_check(self) -> Dict[str, Any]:
        return {
            "federated": self.federated.health_check(),
            "self_training": self.self_trainer.health_check(),
            "replication": self.replication.health_check(),
            "data_generation": self.data_gen.health_check(),
            "sandbox": self.sandbox.health_check(),
            "heterogeneous_compute": self.compute.health_check(),
        }

    def shutdown(self) -> None:
        """Gracefully stop all running containers and close resources."""
        self.sandbox.stop_all()
        self.replication.stop_all()
        self.data_gen.knowledge_graph.close()
        logger.info("EdgeComputeManager shutdown complete")
