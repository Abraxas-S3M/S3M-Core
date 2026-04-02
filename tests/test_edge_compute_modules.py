"""Unit tests for edge compute manager and subsystem modules."""

from __future__ import annotations

import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.edge_compute.api import set_manager
from src.edge_compute.manager import EdgeComputeManager
from src.edge_compute.models import EdgeNodeInfo, OperationType
from src.dashboard.providers.edge_compute_provider import EdgeComputeDashProvider


def test_edge_manager_health_check_and_shutdown(tmp_path) -> None:
    manager = EdgeComputeManager(
        data_output_dir=str(tmp_path / "generated"),
        kg_db_path=str(tmp_path / "kg.db"),
    )
    payload = manager.health_check()
    assert "federated" in payload
    assert "heterogeneous_compute" in payload
    manager.shutdown()


def test_edge_manager_quick_self_training(tmp_path) -> None:
    manager = EdgeComputeManager(
        data_output_dir=str(tmp_path / "generated"),
        kg_db_path=str(tmp_path / "kg.db"),
    )
    labeled_x = np.array([[0.0, 1.0], [1.0, 0.0]], dtype=np.float32)
    labeled_y = np.array([0, 1], dtype=np.int64)
    unlabeled_x = np.array([[0.2, 0.9], [0.8, 0.1]], dtype=np.float32)
    result = manager.quick_self_train(
        input_dim=2,
        output_dim=2,
        labeled_x=labeled_x,
        labeled_y=labeled_y,
        unlabeled_x=unlabeled_x,
        cycles=2,
        epochs_per_cycle=1,
    )
    assert result["cycles_completed"] == 2
    assert len(result["history"]) == 2
    assert "w1" in result["model_params"]


def test_edge_bootstrap_sequence(tmp_path) -> None:
    manager = EdgeComputeManager(
        data_output_dir=str(tmp_path / "generated"),
        kg_db_path=str(tmp_path / "kg.db"),
    )
    params = {"w": np.zeros((2, 2), dtype=np.float32)}
    result = manager.bootstrap_edge_node(
        parent_params=params,
        parent_node_id="parent-1",
        target_memory_mb=2048,
        deploy_sandbox=True,
    )
    assert "replica" in result
    assert "sandbox" in result
    assert result["node_info"]["node_id"] == result["replica"]["replica_id"]


def test_federated_round_and_dp_tracking(tmp_path) -> None:
    manager = EdgeComputeManager(
        data_output_dir=str(tmp_path / "generated"),
        kg_db_path=str(tmp_path / "kg.db"),
    )
    manager.federated.register_node(EdgeNodeInfo(node_id="n1", memory_mb=1024))
    manager.federated.record_round(["n1"], 1.25)
    rounds = manager.federated.round_history()
    assert len(rounds) == 1
    dp = manager.federated.dp_status()
    assert dp["epsilon_spent"] > 0.0


def test_data_generation_and_relationship_discovery(tmp_path) -> None:
    manager = EdgeComputeManager(
        data_output_dir=str(tmp_path / "generated"),
        kg_db_path=str(tmp_path / "kg.db"),
    )
    dataset = manager.data_gen.generate_contrastive_dataset(
        [
            {"text": "alpha record", "label": "alpha"},
            {"text": "bravo record", "label": "bravo"},
        ]
    )
    assert dataset.record_count == 2
    assert os.path.exists(dataset.file_path)
    added = manager.data_gen.discover_relationships(min_count=1, min_pmi=0.0)
    assert added >= 1


def test_compute_execute_matmul(tmp_path) -> None:
    manager = EdgeComputeManager(
        data_output_dir=str(tmp_path / "generated"),
        kg_db_path=str(tmp_path / "kg.db"),
    )

    def _run() -> list[list[float]]:
        return (np.eye(2, dtype=np.float32) @ np.eye(2, dtype=np.float32)).tolist()

    result = manager.compute.execute(OperationType.MATMUL, _run)
    assert result["device"] in {"cpu", "gpu"}
    assert result["result"] == [[1.0, 0.0], [0.0, 1.0]]


def test_edge_dashboard_provider_safe_fallback() -> None:
    set_manager(None)
    provider = EdgeComputeDashProvider()
    payload = provider.get_full_overview()
    assert "edge_network" in payload
    assert "self_training" in payload
    assert payload["edge_network"]["active_nodes"] == 0
