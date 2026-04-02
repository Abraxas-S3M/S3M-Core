"""Unit tests for edge federated learning engine and utilities."""

from __future__ import annotations

import numpy as np

from src.edge_compute.federated_engine import (
    FederatedEngine,
    RDPAccountant,
    decompress_gradient,
    fedavg_aggregate,
    fedprox_local_objective,
    scaffold_correction,
    topk_compress,
)
from src.edge_compute.models import AggregationStrategy, EdgeNodeInfo, NodeStatus


def _params(a: float, b: float) -> dict[str, np.ndarray]:
    return {"w": np.array([a, b], dtype=np.float64)}


def test_topk_compress_and_decompress_roundtrip_with_residual():
    grad = np.array([1.0, -3.0, 2.0, 0.5], dtype=np.float64)
    values, indices, residual = topk_compress(grad, sparsity=0.5)
    restored = decompress_gradient(values, indices, total_size=grad.size)
    assert restored.shape == grad.shape
    assert np.allclose(restored + residual, grad)


def test_topk_error_feedback_accumulates_dropped_dimensions():
    grad = np.array([1.0, 0.2, 0.1, 0.05], dtype=np.float64)
    values_1, indices_1, residual_1 = topk_compress(grad, sparsity=0.75)
    dense_1 = decompress_gradient(values_1, indices_1, total_size=grad.size)
    values_2, indices_2, residual_2 = topk_compress(np.zeros_like(grad), sparsity=0.75, error_feedback=residual_1)
    dense_2 = decompress_gradient(values_2, indices_2, total_size=grad.size)

    assert np.count_nonzero(dense_1) == 1
    assert np.count_nonzero(dense_2) == 1
    assert np.allclose(dense_1 + dense_2 + residual_2, grad)
    assert indices_1[0] != indices_2[0]


def test_fedavg_weighted_aggregate():
    global_params = _params(0.0, 0.0)
    local_updates = [_params(1.0, 3.0), _params(3.0, 5.0)]
    out = fedavg_aggregate(global_params, local_updates, weights=[1.0, 3.0])
    assert np.allclose(out["w"], np.array([2.5, 4.5], dtype=np.float64))


def test_fedprox_local_objective_applies_proximal_term():
    local = _params(2.0, 1.0)
    global_model = _params(1.0, 1.0)
    grad = _params(0.5, -0.5)
    updated = fedprox_local_objective(local, global_model, grad, mu=0.2, lr=0.1)
    expected = np.array([1.93, 1.05], dtype=np.float64)
    assert np.allclose(updated["w"], expected)


def test_scaffold_correction_updates_params_and_controls():
    local = _params(2.0, 3.0)
    global_model = _params(1.0, 1.0)
    local_c = _params(0.2, 0.1)
    global_c = _params(0.1, 0.05)
    grad = _params(1.0, 1.5)
    updated, new_c = scaffold_correction(local, global_model, local_c, global_c, grad, lr=0.1)
    assert np.allclose(updated["w"], np.array([1.91, 2.855], dtype=np.float64))
    assert np.allclose(new_c["w"], np.array([-9.0, -18.5], dtype=np.float64))


def test_rdp_accountant_budget_exhaustion():
    acct = RDPAccountant(epsilon=1.0, delta=1e-5, max_grad_norm=1.0)
    marginal = acct.step(noise_multiplier=1.0, sample_rate=1.0)
    assert marginal > 1.0
    assert acct.budget_exhausted
    status = acct.status()
    assert status["budget_exhausted"] is True
    assert status["epsilon_remaining"] == 0.0


def test_federated_engine_round_progress_with_fedavg(monkeypatch):
    engine = FederatedEngine(
        strategy=AggregationStrategy.FEDAVG,
        min_nodes=2,
        compression_sparsity=0.0,
        dp_max_grad_norm=10.0,
    )
    engine.initialize_global_model(_params(0.0, 0.0))
    monkeypatch.setattr(engine._dp_accountant, "add_noise", lambda gradients, noise_multiplier=1.0: gradients)

    local_updates = {
        "n1": _params(1.0, 3.0),
        "n2": _params(3.0, 5.0),
    }
    fed_round = engine.run_round(local_updates, sample_counts={"n1": 1, "n2": 3})
    params = engine.get_global_params()

    assert fed_round.round_id == 1
    assert fed_round.gradients_compressed is True
    assert fed_round.dp_applied is True
    assert np.allclose(params["w"], np.array([2.5, 4.5], dtype=np.float64), atol=1e-6)


def test_federated_engine_halts_when_budget_exhausted():
    engine = FederatedEngine(
        strategy=AggregationStrategy.FEDAVG,
        min_nodes=2,
        compression_sparsity=0.0,
        dp_epsilon=1.0,
    )
    engine.initialize_global_model(_params(0.0, 0.0))
    engine._dp_accountant._spent_epsilon = 1.0
    fed_round = engine.run_round({"n1": _params(1.0, 1.0), "n2": _params(1.0, 1.0)})
    assert fed_round.round_id == 0
    assert len(engine.round_history()) == 0


def test_active_nodes_filtering():
    engine = FederatedEngine(min_nodes=1)
    n1 = EdgeNodeInfo(node_id="a", hostname="alpha", status=NodeStatus.ONLINE)
    n2 = EdgeNodeInfo(node_id="b", hostname="beta", status=NodeStatus.TRAINING)
    n3 = EdgeNodeInfo(node_id="c", hostname="gamma", status=NodeStatus.OFFLINE)
    engine.register_node(n1)
    engine.register_node(n2)
    engine.register_node(n3)
    active = engine.active_nodes()
    assert {node.node_id for node in active} == {"a", "b"}


def test_hierarchical_strategy_runs_and_updates_round_history(monkeypatch):
    engine = FederatedEngine(strategy=AggregationStrategy.HIERARCHICAL, min_nodes=2, compression_sparsity=0.0)
    engine.initialize_global_model(_params(0.0, 0.0))
    monkeypatch.setattr(engine._dp_accountant, "add_noise", lambda gradients, noise_multiplier=1.0: gradients)

    local_updates = {
        "node-a": _params(1.0, 1.0),
        "node-b": _params(2.0, 2.0),
        "node-c": _params(3.0, 3.0),
        "node-d": _params(4.0, 4.0),
    }
    fed_round = engine.run_round(local_updates)
    assert fed_round.round_id == 1
    assert len(engine.round_history()) == 1
    params = engine.get_global_params()
    assert "w" in params
    assert params["w"].shape == (2,)
