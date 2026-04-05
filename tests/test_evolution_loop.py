"""Tests for S3M continuous evolution and model governance loop."""

from __future__ import annotations

from src.evolution.continuous_loop import ContinuousEvolutionLoop, EvolutionConfig
from src.evolution.experience_replay import Experience, PrioritizedReplayBuffer
from src.evolution.model_versioner import ModelVersioner
from src.training.online_learning.stream_learner import StreamConfig, StreamLearner


def test_replay_buffer_add_sample_and_update() -> None:
    replay = PrioritizedReplayBuffer(capacity=200, seed=42)
    for i in range(60):
        replay.add(
            Experience(
                state={"x": float(i)},
                action="act",
                reward=float(i) * 0.1,
                td_error=max(0.01, float(i) * 0.01),
            )
        )
    assert replay.size() == 60
    experiences, weights, indices = replay.sample(10)
    assert len(experiences) == 10
    assert len(weights) == 10
    assert len(indices) == 10
    replay.update_priorities(indices, [1.0] * len(indices))


def test_replay_buffer_state_roundtrip() -> None:
    replay = PrioritizedReplayBuffer(capacity=150, seed=7)
    for i in range(25):
        replay.add(Experience(state={"i": i}, td_error=0.2 + i * 0.01))
    state = replay.export_state()

    restored = PrioritizedReplayBuffer(capacity=150, seed=8)
    restored.load_state(state)
    assert restored.size() == replay.size()
    sampled, _, _ = restored.sample(5)
    assert len(sampled) == 5


def test_model_versioner_stage_promote_rollback() -> None:
    versioner = ModelVersioner(model_name="test_model")
    v1 = versioner.stage(metrics={"accuracy": 0.85, "loss": 0.3}, notes="baseline")
    assert versioner.promote(v1.version_id)["promoted"] is True

    v2 = versioner.stage(metrics={"accuracy": 0.90, "loss": 0.2}, notes="improved")
    assert versioner.promote(v2.version_id)["promoted"] is True
    assert versioner.get_active() is not None
    assert versioner.get_active().version_number == 2  # type: ignore[union-attr]

    rolled_back = versioner.rollback()
    assert rolled_back["rolled_back"] is True
    assert versioner.get_active() is not None
    assert versioner.get_active().version_number == 1  # type: ignore[union-attr]


def test_model_versioner_regression_detection() -> None:
    versioner = ModelVersioner(regression_threshold=0.1)
    base = versioner.stage(metrics={"accuracy": 0.90, "loss": 0.20})
    versioner.promote(base.version_id)
    degraded = versioner.stage(metrics={"accuracy": 0.70, "loss": 0.30})
    result = versioner.promote(degraded.version_id)
    assert result["regression_detected"] is True


def test_continuous_loop_full_cycle_and_checkpoint(tmp_path) -> None:
    learner = StreamLearner(StreamConfig(feature_dimension=32, n_trees=3))
    loop = ContinuousEvolutionLoop(
        learner=learner,
        config=EvolutionConfig(
            retrain_interval_samples=10,
            replay_batch_size=4,
            checkpoint_dir=str(tmp_path / "evolution_ckpt"),
        ),
    )

    triggered = 0
    for i in range(25):
        cycle = loop.ingest(
            Experience(
                state={"x": float(i), "bias": 1.0},
                action="hold",
                reward=float(i % 2),
                td_error=0.5,
            )
        )
        if cycle is not None:
            triggered += 1
    assert triggered >= 2

    stats = loop.get_stats()
    assert stats["total_samples"] == 25
    assert stats["replay_buffer_size"] == 25

    checkpoint = loop.save_checkpoint()
    restored = ContinuousEvolutionLoop(
        learner=StreamLearner(StreamConfig(feature_dimension=32, n_trees=3)),
        config=EvolutionConfig(
            retrain_interval_samples=10,
            replay_batch_size=4,
            checkpoint_dir=str(tmp_path / "evolution_ckpt"),
        ),
    )
    restored.load_checkpoint(checkpoint)
    restored_stats = restored.get_stats()
    assert restored_stats["total_samples"] == 25
    assert restored_stats["replay_buffer_size"] == 25

