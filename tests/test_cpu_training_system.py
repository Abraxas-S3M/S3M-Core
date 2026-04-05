"""Tests for the CPU-first training stack."""

from __future__ import annotations

import pytest

try:
    import numpy as np

    NP_AVAILABLE = True
except Exception:  # pragma: no cover - optional runtime
    NP_AVAILABLE = False

from src.training.distributed_cpu.cluster_trainer import ClusterTrainer, ClusterTrainingConfig
from src.training.online_learning.stream_learner import (
    OnlineSGDClassifier,
    OnlineTreeEnsemble,
    StreamConfig,
    StreamLearner,
)
from src.training.sparse_moe.cpu_moe import MoEConfig, MoEInferenceEngine

pytestmark = pytest.mark.skipif(not NP_AVAILABLE, reason="NumPy required")


def test_online_sgd_learns() -> None:
    sgd = OnlineSGDClassifier(StreamConfig(feature_dimension=32))
    losses = []
    for i in range(200):
        x = float(i % 2)
        features = {"x": x, "bias": 1.0}
        label = x
        losses.append(sgd.update(features, label))
    assert losses[-1] < losses[0]


def test_online_tree_ensemble_predicts_float() -> None:
    trees = OnlineTreeEnsemble(n_trees=5, max_depth=4)
    for i in range(100):
        trees.update({"a": float(i), "b": float(i * 2)}, float(i % 2))
    prediction = trees.predict({"a": 50.0, "b": 100.0})
    assert isinstance(prediction, float)


def test_stream_learner_checkpoint_roundtrip(tmp_path) -> None:
    learner = StreamLearner(StreamConfig(feature_dimension=64, n_trees=3, window_size=200))
    for i in range(80):
        feats = {"sensor_1": float(i % 5), "sensor_2": float(i % 3)}
        learner.learn(feats, float(i % 2))
    before = learner.get_metrics()
    path = learner.save_checkpoint(str(tmp_path / "stream.json"))

    restored = StreamLearner(StreamConfig(feature_dimension=64, n_trees=3, window_size=200))
    restored.load_checkpoint(path)
    after = restored.get_metrics()
    assert int(after["total_samples"]) == int(before["total_samples"])
    assert after["avg_loss"] >= 0.0


def test_sparse_moe_inference_checkpoint(tmp_path) -> None:
    engine = MoEInferenceEngine(MoEConfig(n_experts=8, top_k=2, input_dim=32, output_dim=16, expert_hidden_dim=16))
    out1 = engine.infer({"threat_speed": 1.5, "heading_delta": -0.3})
    assert out1.shape == (16,)

    checkpoint = engine.save_checkpoint(str(tmp_path / "moe.json"))
    restored = MoEInferenceEngine(MoEConfig(n_experts=8, top_k=2, input_dim=32, output_dim=16, expert_hidden_dim=16))
    restored.load_checkpoint(checkpoint)
    out2 = restored.infer({"threat_speed": 1.5, "heading_delta": -0.3})
    assert out2.shape == (16,)
    assert restored.stats()["inference_count"] >= 1


def test_cluster_trainer_train_and_resume(tmp_path) -> None:
    config = ClusterTrainingConfig(
        n_workers=2,
        feature_dimension=32,
        batch_size=16,
        max_epochs=2,
        checkpoint_every_steps=3,
        checkpoint_dir=str(tmp_path / "cluster_ckpt"),
        seed=42,
    )
    trainer = ClusterTrainer(config)
    dataset = [
        ({"f1": float(i % 7), "f2": float((i * 2) % 5), "bias": 1.0}, float((i % 2)))
        for i in range(120)
    ]
    result = trainer.train(dataset)
    assert result["step"] > 0
    assert result["avg_loss"] >= 0.0

    checkpoint = trainer.save_checkpoint()
    resumed = ClusterTrainer(config)
    resumed.load_checkpoint(checkpoint.path)
    resumed_result = resumed.train(dataset, epochs=1)
    assert resumed_result["epoch"] >= result["epoch"]
    assert resumed.stats()["step"] > result["step"]

