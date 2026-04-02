#!/usr/bin/env python3
# File: scripts/demo_edge_compute.py
"""
S3M Edge Compute Demo
UNCLASSIFIED - FOUO

Demonstrates both novel features end-to-end using synthetic data:
  Feature 1: Edge CPU Network - federated learning, self-training, data gen, sandbox
  Feature 2: Heterogeneous Compute - adaptive GPU<->CPU scheduling
"""

from __future__ import annotations

import os
import sys
import time

import numpy as np

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from src.edge_compute.manager import EdgeComputeManager
from src.edge_compute.models import (
    AggregationStrategy,
    EdgeNodeInfo,
    NodeStatus,
    OperationType,
    SchedulingPolicy,
    SelfTrainingStrategy,
)
from src.edge_compute.self_training import NumpyLinearModel


def separator(title: str) -> None:
    print(f"\n{'='*70}")
    print(f"  {title}")
    print(f"{'='*70}\n")


def demo_feature1_federated(manager: EdgeComputeManager) -> None:
    """Demonstrate federated learning with 3 simulated edge nodes."""
    separator("Feature 1A: Federated Learning (FedProx + TopK + DP)")

    # Initialize a global model
    input_dim, hidden_dim, output_dim = 16, 32, 4
    global_model = NumpyLinearModel(input_dim, hidden_dim, output_dim)
    manager.federated.initialize_global_model(global_model.params)

    # Register 3 simulated nodes
    nodes = []
    for i in range(3):
        node = EdgeNodeInfo(
            hostname=f"edge-node-{i}",
            ip_address=f"192.168.1.{10+i}",
            cpu_cores=4,
            memory_mb=4096,
            status=NodeStatus.ONLINE,
        )
        manager.federated.register_node(node)
        nodes.append(node)
        print(f"  Registered node: {node.hostname} ({node.node_id[:8]})")

    # Simulate 3 federated rounds
    for round_num in range(3):
        print(f"\n  --- Round {round_num + 1} ---")
        local_updates = {}
        sample_counts = {}

        for node in nodes:
            # Each node does local SGD on synthetic data
            x = np.random.randn(100, input_dim).astype(np.float32)
            y_classes = np.random.randint(0, output_dim, size=100)
            y_onehot = np.zeros((100, output_dim), dtype=np.float32)
            y_onehot[np.arange(100), y_classes] = 1.0

            local_model = NumpyLinearModel(input_dim, hidden_dim, output_dim)
            local_model.params = manager.federated.get_global_params()

            for _ in range(3):
                grads = local_model.compute_gradients(x, y_onehot)
                local_model.apply_gradients(grads, lr=0.001)

            local_updates[node.node_id] = local_model.params
            sample_counts[node.node_id] = 100

        fed_round = manager.federated.run_round(local_updates, sample_counts)
        dp = manager.federated.dp_status()
        print(f"  Aggregated {len(fed_round.participating_nodes)} nodes in {fed_round.duration_seconds:.3f}s")
        print(f"  DP budget: epsilon spent={dp['epsilon_spent']:.4f} / {dp['epsilon_budget']}")


def demo_feature1_self_training(manager: EdgeComputeManager) -> None:
    """Demonstrate Noisy Student self-training."""
    separator("Feature 1B: Noisy Student Self-Training")

    input_dim, output_dim = 16, 4
    labeled_x = np.random.randn(50, input_dim).astype(np.float32)
    labeled_classes = np.random.randint(0, output_dim, size=50)
    labeled_y = np.zeros((50, output_dim), dtype=np.float32)
    labeled_y[np.arange(50), labeled_classes] = 1.0
    unlabeled_x = np.random.randn(500, input_dim).astype(np.float32)

    result = manager.quick_self_train(
        input_dim=input_dim,
        output_dim=output_dim,
        labeled_x=labeled_x,
        labeled_y=labeled_y,
        unlabeled_x=unlabeled_x,
        cycles=5,
    )

    print(f"  Completed {result['cycles_completed']} self-training cycles")
    total_pseudo = sum(h["sample_count"] for h in result["history"])
    print(f"  Total pseudo-labels generated: {total_pseudo}")
    if result["history"]:
        avg_conf = np.mean([h["avg_confidence"] for h in result["history"] if h["avg_confidence"] > 0])
        print(f"  Average pseudo-label confidence: {avg_conf:.3f}")


def demo_feature1_data_gen(manager: EdgeComputeManager) -> None:
    """Demonstrate autonomous data generation and knowledge graph."""
    separator("Feature 1C: Autonomous Data Generation & Knowledge Graph")

    # Contrastive augmentation
    data = np.random.randn(1000, 16).astype(np.float32)
    ds_contrastive = manager.data_gen.generate_contrastive_dataset(data, n_pairs=2000)
    print(f"  Contrastive dataset: {ds_contrastive.record_count} pairs ({ds_contrastive.file_size_bytes} bytes)")

    # Generative replay
    class_features = {
        0: np.random.randn(200, 16).astype(np.float32),
        1: np.random.randn(200, 16).astype(np.float32) + 2.0,
        2: np.random.randn(200, 16).astype(np.float32) - 1.5,
    }
    ds_replay = manager.data_gen.generate_replay_dataset(class_features, n_per_class=300)
    print(f"  Replay dataset: {ds_replay.record_count} samples ({ds_replay.file_size_bytes} bytes)")

    # Entity linking and knowledge graph
    entities = [
        {"name": "T-72 Tank", "type": "vehicle", "context": "armored"},
        {"name": "RPG-7", "type": "weapon", "context": "anti-tank"},
        {"name": "T-72 Tank", "type": "vehicle", "context": "engagement"},
        {"name": "RPG-7", "type": "weapon", "context": "engagement"},
        {"name": "BMP-2", "type": "vehicle", "context": "armored"},
        {"name": "T-72 Tank", "type": "vehicle", "context": "convoy"},
        {"name": "BMP-2", "type": "vehicle", "context": "convoy"},
        {"name": "RPG-7", "type": "weapon", "context": "ambush"},
        {"name": "T-72 Tank", "type": "vehicle", "context": "ambush"},
    ]
    added = manager.data_gen.ingest_entities(entities, co_occurrence_window=3)
    print(f"  Entities ingested: {added}")

    new_edges = manager.data_gen.discover_relationships(min_count=2, min_pmi=0.5)
    print(f"  PMI edges discovered: {new_edges}")

    kg_stats = manager.data_gen.knowledge_graph.stats()
    print(f"  Knowledge graph: {kg_stats['entities']} entities, {kg_stats['edges']} edges")

    neighbors = manager.data_gen.knowledge_graph.query_neighbors("T-72 Tank")
    for n in neighbors:
        print(f"    -> {n['name']} ({n['relation']}, conf={n['confidence']:.2f})")


def demo_feature1_sandbox(manager: EdgeComputeManager) -> None:
    """Demonstrate sandbox deployment and parameter toggling."""
    separator("Feature 1D: Sandbox Deployment & Parameter Toggling")

    sandbox = manager.sandbox.deploy(
        cpu_cores=2,
        memory_mb=2048,
        gpu_passthrough=False,
        params={"temperature": 0.7, "training_enabled": True},
    )
    print(f"  Sandbox deployed: {sandbox.sandbox_id[:8]}")
    print(f"  Running: {sandbox.running}")
    print(f"  Initial params: temperature={sandbox.parameters.get('temperature')}")

    # Toggle parameters
    updated = manager.sandbox.update_params(
        sandbox.sandbox_id,
        {"temperature": 0.3, "training_enabled": False, "max_inference_batch": 64},
    )
    print(f"  Updated params: temperature={updated['temperature']}, training={updated['training_enabled']}")

    print(f"  Sandbox health: {manager.sandbox.health_check()}")


def demo_feature2_hetero_compute(manager: EdgeComputeManager) -> None:
    """Demonstrate adaptive GPU<->CPU task scheduling."""
    separator("Feature 2: Heterogeneous Compute (Adaptive Scheduler)")

    # Define some dummy operations
    def cpu_tokenize(data: np.ndarray) -> np.ndarray:
        time.sleep(0.001)  # Simulate tokenization
        return data.astype(np.int32)

    def matmul_op(data: np.ndarray) -> np.ndarray:
        return data @ data.T

    def attention_op(data: np.ndarray) -> np.ndarray:
        scores = data @ data.T / np.sqrt(data.shape[-1])
        weights = np.exp(scores) / np.exp(scores).sum(axis=-1, keepdims=True)
        return weights @ data

    # Run tasks through the scheduler
    data = np.random.randn(32, 64).astype(np.float32)

    ops_to_test = [
        (OperationType.TOKENIZATION, cpu_tokenize),
        (OperationType.MATMUL, matmul_op),
        (OperationType.ATTENTION, attention_op),
        (OperationType.PREPROCESSING, lambda x: x / x.max()),
        (OperationType.MATMUL, matmul_op),
        (OperationType.ATTENTION, attention_op),
        (OperationType.TOKENIZATION, cpu_tokenize),
        (OperationType.EMBEDDING, lambda x: x * 0.5),
        (OperationType.MATMUL, matmul_op),
        (OperationType.POSTPROCESSING, lambda x: np.argmax(x, axis=-1)),
    ]

    print(f"  Capabilities: {manager.compute.caps.to_dict()}")
    print(f"  Policy: {manager.compute.policy.value}")
    print()

    for op_type, func in ops_to_test:
        result = manager.compute.execute(op_type, func, data)
        print(f"  {op_type.value:20s} -> shape={getattr(result, 'shape', 'scalar')}")

    print()
    stats = manager.compute.device_stats()
    print(f"  CPU tasks: {stats['cpu']['tasks_completed']}, avg_latency: {stats['cpu']['avg_latency_ms']:.2f} ms")
    print(f"  GPU tasks: {stats['gpu']['tasks_completed']}, avg_latency: {stats['gpu']['avg_latency_ms']:.2f} ms")
    print(f"  Total tasks: {stats['total_tasks']}")

    policy = manager.compute.scheduler.get_policy_table()
    print(f"\n  Learned policy table:")
    for op, devices in policy.items():
        print(f"    {op:20s} -> {devices}")


def main() -> None:
    print("=" * 70)
    print("  S3M Edge Compute Demo - Two Novel Features")
    print("  UNCLASSIFIED - FOUO")
    print("=" * 70)

    manager = EdgeComputeManager(
        aggregation_strategy=AggregationStrategy.FEDPROX,
        dp_epsilon=8.0,
        compression_sparsity=0.9,
        self_training_strategy=SelfTrainingStrategy.NOISY_STUDENT,
        confidence_threshold=0.7,  # Lower for demo to get more pseudo-labels
        scheduling_policy=SchedulingPolicy.ADAPTIVE,
        data_output_dir="data/edge/demo_generated/",
        kg_db_path="data/edge/demo_knowledge.db",
    )

    try:
        demo_feature1_federated(manager)
        demo_feature1_self_training(manager)
        demo_feature1_data_gen(manager)
        demo_feature1_sandbox(manager)
        demo_feature2_hetero_compute(manager)

        separator("Full System Health Check")
        health = manager.health_check()
        for subsystem, status in health.items():
            print(f"  {subsystem}:")
            if isinstance(status, dict):
                for k, v in status.items():
                    if not isinstance(v, dict):
                        print(f"    {k}: {v}")
            print()

    finally:
        manager.shutdown()

    print("\nDemo complete.")


if __name__ == "__main__":
    main()
