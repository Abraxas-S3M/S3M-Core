"""Unit tests for the S3M self-replication engine."""

from __future__ import annotations

import os

import numpy as np
import pytest

from src.edge_compute.models import NodeStatus
from src.edge_compute.self_replication import ReplicationEngine


def _sample_params() -> dict[str, np.ndarray]:
    return {
        "w1": np.arange(0, 64, dtype=np.float32).reshape(8, 8),
        "b1": np.arange(0, 8, dtype=np.float32),
    }


def test_compute_distillation_ratio_clamps_to_bounds() -> None:
    ratio_small = ReplicationEngine.compute_distillation_ratio(
        target_memory_mb=128,
        parent_model_size_mb=4096.0,
        min_ratio=0.2,
        max_ratio=1.0,
    )
    ratio_large = ReplicationEngine.compute_distillation_ratio(
        target_memory_mb=32768,
        parent_model_size_mb=1.0,
        min_ratio=0.2,
        max_ratio=1.0,
    )
    assert ratio_small == 0.2
    assert ratio_large == 1.0


def test_create_replica_offline_runtime_exports_quantized_model() -> None:
    engine = ReplicationEngine(container_runtime="docker")
    # Keep the test offline and deterministic.
    engine._runtime_available = False  # pylint: disable=protected-access

    spec = engine.create_replica(
        parent_node_id="node-alpha",
        parent_params=_sample_params(),
        target_memory_mb=512,
        target_cpu_cores=2,
    )

    assert spec.parent_node_id == "node-alpha"
    assert spec.status == NodeStatus.OFFLINE
    assert spec.quantization == "int8"
    assert spec.container_id == ""
    assert os.path.exists(spec.model_snapshot_path)

    loaded = ReplicationEngine.load_model_snapshot(spec.model_snapshot_path)
    assert loaded["w1"].dtype == np.int8
    assert loaded["b1"].dtype == np.int8
    assert "w1__scale" in np.load(spec.model_snapshot_path).files

    restored = ReplicationEngine.load_model_snapshot(spec.model_snapshot_path, dequantize=True)
    assert restored["w1"].shape[0] <= 8
    assert restored["w1"].dtype == np.float32


def test_launch_container_path_returns_online_state(monkeypatch: pytest.MonkeyPatch) -> None:
    engine = ReplicationEngine(container_runtime="docker")
    engine._runtime_available = True  # pylint: disable=protected-access

    def _fake_launch(**_: object) -> str:
        return "abc123def456"

    monkeypatch.setattr(engine, "_launch_container", _fake_launch)
    spec = engine.create_replica(
        parent_node_id="node-bravo",
        parent_params=_sample_params(),
        target_memory_mb=2048,
        target_cpu_cores=4,
        env_vars={"S3M_ROLE": "replica"},
    )
    assert spec.status == NodeStatus.ONLINE
    assert spec.container_id == "abc123def456"


def test_rejects_invalid_env_var_name() -> None:
    engine = ReplicationEngine(container_runtime="docker")
    with pytest.raises(ValueError):
        engine.create_replica(
            parent_node_id="node-charlie",
            parent_params=_sample_params(),
            env_vars={"bad-key": "x"},
        )
