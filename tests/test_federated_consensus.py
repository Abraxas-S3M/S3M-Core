"""Unit tests for S3M Federated Adapter Consensus Protocol (FACP)."""

from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import importlib.util
from pathlib import Path
import sys

import numpy as np

MODULE_PATH = Path(__file__).resolve().parents[1] / "src" / "training" / "cpu_adaptation" / "federated_consensus.py"
MODULE_SPEC = importlib.util.spec_from_file_location("federated_consensus_under_test", MODULE_PATH)
if MODULE_SPEC is None or MODULE_SPEC.loader is None:  # pragma: no cover - defensive guard
    raise RuntimeError(f"Unable to load module from {MODULE_PATH}")
MODULE = importlib.util.module_from_spec(MODULE_SPEC)
sys.modules[MODULE_SPEC.name] = MODULE
MODULE_SPEC.loader.exec_module(MODULE)

FederatedAdapterConsensus = MODULE.FederatedAdapterConsensus
NodeAdapterUpdate = MODULE.NodeAdapterUpdate


def _make_chain(parent_hash: str, depth: int = 2) -> list[str]:
    first = hashlib.sha256(parent_hash.encode("utf-8")).hexdigest()
    chain = [first]
    for _ in range(depth - 1):
        chain.append(hashlib.sha256(chain[-1].encode("utf-8")).hexdigest())
    return chain


def _make_update(
    node_id: str,
    weights: dict[str, np.ndarray],
    config_hash: str,
    parent_hash: str,
    *,
    hardware_tier: str = "fixed_site",
    training_loss: float = 0.25,
    weight_hash: str | None = None,
    attestation_chain: list[str] | None = None,
) -> NodeAdapterUpdate:
    computed_hash = weight_hash or FederatedAdapterConsensus.compute_weight_hash(weights)
    return NodeAdapterUpdate(
        node_id=node_id,
        hardware_tier=hardware_tier,
        adapter_weights=weights,
        training_loss=training_loss,
        num_samples=64,
        training_steps=10,
        precision_used="fp32",
        timestamp=datetime.now(timezone.utc).isoformat(),
        weight_hash=computed_hash,
        training_config_hash=config_hash,
        parent_model_hash=parent_hash,
        attestation_chain=attestation_chain if attestation_chain is not None else _make_chain(parent_hash),
    )


def test_facp_rejects_byzantine_outlier_and_merges_trusted_nodes() -> None:
    config_hash = hashlib.sha256(b"cfg").hexdigest()
    bad_config_hash = hashlib.sha256(b"cfg-bad").hexdigest()
    parent_hash = hashlib.sha256(b"base-model").hexdigest()
    facp = FederatedAdapterConsensus(
        min_participants=2,
        byzantine_threshold=0.45,
        expected_parent_model_hash=parent_hash,
        valid_training_config_hashes=[config_hash],
    )

    n1 = _make_update(
        "node-1",
        {"layer.a": np.array([1.0, 1.0], dtype=np.float32), "layer.b": np.array([0.20], dtype=np.float32)},
        config_hash,
        parent_hash,
        hardware_tier="fixed_site",
        training_loss=0.20,
    )
    n2 = _make_update(
        "node-2",
        {"layer.a": np.array([1.1, 0.9], dtype=np.float32), "layer.b": np.array([0.30], dtype=np.float32)},
        config_hash,
        parent_hash,
        hardware_tier="edge_gpu",
        training_loss=0.22,
    )
    n3 = _make_update(
        "node-3",
        {"layer.a": np.array([100.0, -100.0], dtype=np.float32), "layer.b": np.array([50.0], dtype=np.float32)},
        bad_config_hash,
        parent_hash,
        hardware_tier="cpu_austere",
        training_loss=8.0,
    )

    assert facp.register_update(n1) is True
    assert facp.register_update(n2) is True
    assert facp.register_update(n3) is True

    result = facp.aggregate()

    assert set(result.participating_nodes) == {"node-1", "node-2"}
    assert "node-3" in result.rejected_nodes
    assert result.rejection_reasons["node-3"] == "byzantine_threshold"
    np.testing.assert_allclose(result.merged_weights["layer.a"], np.array([1.05, 0.95], dtype=np.float32), atol=0.20)
    assert result.consensus_confidence > 0.80


def test_facp_register_update_rejects_weight_hash_mismatch() -> None:
    config_hash = hashlib.sha256(b"cfg").hexdigest()
    parent_hash = hashlib.sha256(b"base-model").hexdigest()
    facp = FederatedAdapterConsensus(
        min_participants=1,
        expected_parent_model_hash=parent_hash,
        valid_training_config_hashes=[config_hash],
    )
    update = _make_update(
        "node-bad",
        {"layer.a": np.array([1.0, 2.0], dtype=np.float32)},
        config_hash,
        parent_hash,
        weight_hash="0" * 64,
    )

    assert facp.register_update(update) is False
    result = facp.aggregate()
    assert "node-bad" in result.rejected_nodes
    assert result.rejection_reasons["node-bad"] == "weight_hash_mismatch"


def test_weizsfeld_geometric_median_handles_zero_distance_case() -> None:
    config_hash = hashlib.sha256(b"cfg").hexdigest()
    parent_hash = hashlib.sha256(b"base-model").hexdigest()
    facp = FederatedAdapterConsensus(
        min_participants=2,
        expected_parent_model_hash=parent_hash,
        valid_training_config_hashes=[config_hash],
    )
    weights = {"layer.same": np.array([2.0, 2.0], dtype=np.float32)}
    median = facp._compute_geometric_median([weights, weights, weights], max_iters=20, tol=1e-8)
    np.testing.assert_allclose(median["layer.same"], np.array([2.0, 2.0], dtype=np.float32), atol=1e-6)
    assert np.isfinite(median["layer.same"]).all()


def test_facp_supports_partial_layer_updates() -> None:
    config_hash = hashlib.sha256(b"cfg").hexdigest()
    parent_hash = hashlib.sha256(b"base-model").hexdigest()
    facp = FederatedAdapterConsensus(
        min_participants=2,
        byzantine_threshold=0.10,
        expected_parent_model_hash=parent_hash,
        valid_training_config_hashes=[config_hash],
    )
    updates = [
        _make_update("node-a", {"layer.a": np.array([1.0, 1.0], dtype=np.float32)}, config_hash, parent_hash),
        _make_update("node-b", {"layer.b": np.array([2.0], dtype=np.float32)}, config_hash, parent_hash),
        _make_update(
            "node-c",
            {"layer.a": np.array([1.2, 0.8], dtype=np.float32), "layer.b": np.array([1.8], dtype=np.float32)},
            config_hash,
            parent_hash,
        ),
    ]
    for update in updates:
        assert facp.register_update(update) is True

    result = facp.aggregate()
    assert set(result.merged_weights.keys()) == {"layer.a", "layer.b"}
    assert len(result.participating_nodes) >= 2


def test_facp_limits_maximum_nodes_per_round() -> None:
    config_hash = hashlib.sha256(b"cfg").hexdigest()
    parent_hash = hashlib.sha256(b"base-model").hexdigest()
    facp = FederatedAdapterConsensus(
        min_participants=1,
        expected_parent_model_hash=parent_hash,
        valid_training_config_hashes=[config_hash],
    )
    for idx in range(100):
        update = _make_update(
            f"node-{idx}",
            {"layer.a": np.array([float(idx)], dtype=np.float32)},
            config_hash,
            parent_hash,
        )
        assert facp.register_update(update) is True

    overflow = _make_update("node-overflow", {"layer.a": np.array([101.0], dtype=np.float32)}, config_hash, parent_hash)
    assert facp.register_update(overflow) is False
    result = facp.aggregate()
    assert "node-overflow" in result.rejected_nodes
    assert result.rejection_reasons["node-overflow"] == "max_nodes_exceeded"

