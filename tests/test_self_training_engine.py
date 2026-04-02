"""Tests for edge self-training engine and numpy fallback model.

Covers:
  1) Noise augmentation utilities
  2) NumpyLinearModel forward/training/distillation
  3) Pseudo-label strategy cycles
  4) Noisy student bi-directional teacher refresh
  5) Co-training cross-label cycle
"""

from __future__ import annotations

import numpy as np
import pytest

from src.edge_compute.models import SelfTrainingStrategy
from src.edge_compute.self_training import (
    NumpyLinearModel,
    SelfTrainingEngine,
    apply_noise_chain,
    dropout_noise,
    gaussian_noise,
    mixup,
)


@pytest.fixture
def seeded() -> None:
    np.random.seed(7)


def _onehot(y: np.ndarray, classes: int) -> np.ndarray:
    out = np.zeros((len(y), classes), dtype=np.float32)
    out[np.arange(len(y)), y] = 1.0
    return out


def _make_dataset(n: int = 64, in_dim: int = 6, classes: int = 3):
    x = np.random.randn(n, in_dim).astype(np.float32)
    logits = np.stack(
        [
            x[:, 0] + 0.5 * x[:, 1],
            -x[:, 2] + 0.25 * x[:, 3],
            x[:, 4] - x[:, 5],
        ],
        axis=1,
    )
    y_idx = logits.argmax(axis=1) % classes
    return x, _onehot(y_idx, classes)


def test_noise_utilities_shape_and_validation(seeded) -> None:
    x = np.ones((4, 3), dtype=np.float32)

    out_drop = dropout_noise(x, rate=0.25)
    assert out_drop.shape == x.shape

    out_gauss = gaussian_noise(x, std=0.1)
    assert out_gauss.shape == x.shape

    mixed, lam = mixup(x, x * 2.0, alpha=0.3)
    assert mixed.shape == x.shape
    assert 0.0 <= lam <= 1.0

    chained = apply_noise_chain(x, dropout_rate=0.1, gaussian_std=0.05)
    assert chained.shape == x.shape

    with pytest.raises(ValueError):
        dropout_noise(x, rate=1.0)
    with pytest.raises(ValueError):
        gaussian_noise(x, std=-0.1)


def test_numpy_linear_model_training_step(seeded) -> None:
    model = NumpyLinearModel(input_dim=6, hidden_dim=12, output_dim=3)
    x, y = _make_dataset(n=32, in_dim=6, classes=3)

    probs = model.forward(x)
    assert probs.shape == (32, 3)
    assert np.allclose(probs.sum(axis=1), 1.0, atol=1e-5)

    grads = model.compute_gradients(x, y, lr=0.01)
    assert set(grads.keys()) == {"W1", "b1", "W2", "b2"}

    before = model.params["W1"].copy()
    loss_proxy = model.apply_gradients(grads, lr=0.01)
    assert loss_proxy > 0.0
    assert not np.allclose(before, model.params["W1"])

    student = model.distill_to(ratio=0.5)
    assert student.hidden_dim < model.hidden_dim
    assert student.output_dim == model.output_dim


def test_generate_pseudo_labels_respects_cap(seeded) -> None:
    model = NumpyLinearModel(input_dim=6, hidden_dim=10, output_dim=3)
    engine = SelfTrainingEngine(
        strategy=SelfTrainingStrategy.PSEUDO_LABEL,
        confidence_threshold=0.0,
        max_pseudo_per_cycle=5,
    )
    engine.initialize(model)

    unlabeled = np.random.randn(20, 6).astype(np.float32)
    x_sel, y_sel, conf = engine.generate_pseudo_labels(unlabeled)
    assert x_sel.shape[0] == 5
    assert y_sel.shape == (5, 3)
    assert conf.shape[0] == 5


def test_noisy_student_cycle_and_teacher_refresh(seeded) -> None:
    model = NumpyLinearModel(input_dim=6, hidden_dim=16, output_dim=3)
    labeled_x, labeled_y = _make_dataset(n=40, in_dim=6, classes=3)
    unlabeled_x = np.random.randn(80, 6).astype(np.float32)

    engine = SelfTrainingEngine(
        strategy=SelfTrainingStrategy.NOISY_STUDENT,
        confidence_threshold=0.0,
        teacher_update_interval=2,
        max_pseudo_per_cycle=25,
        mixup_alpha=0.2,
        learning_rate=0.005,
    )
    engine.initialize(model)

    teacher_before = engine.get_teacher().params["W1"].copy()  # type: ignore[union-attr]
    batch1 = engine.train_cycle(labeled_x, labeled_y, unlabeled_x, epochs=2)
    assert batch1.sample_count > 0
    assert batch1.noise_applied is True

    batch2 = engine.train_cycle(labeled_x, labeled_y, unlabeled_x, epochs=2)
    assert batch2.sample_count > 0

    teacher_after = engine.get_teacher().params["W1"]  # type: ignore[union-attr]
    assert not np.allclose(teacher_before, teacher_after)

    health = engine.health_check()
    assert health["cycle"] == 2
    assert health["total_pseudo_labels"] >= batch1.sample_count + batch2.sample_count


def test_pseudo_label_cycle_records_history(seeded) -> None:
    model = NumpyLinearModel(input_dim=6, hidden_dim=16, output_dim=3)
    labeled_x, labeled_y = _make_dataset(n=30, in_dim=6, classes=3)
    unlabeled_x = np.random.randn(40, 6).astype(np.float32)

    engine = SelfTrainingEngine(
        strategy=SelfTrainingStrategy.PSEUDO_LABEL,
        confidence_threshold=0.0,
        max_pseudo_per_cycle=15,
    )
    engine.initialize(model)

    batch = engine.train_cycle(labeled_x, labeled_y, unlabeled_x, epochs=1)
    assert batch.sample_count == 15
    assert batch.noise_applied is False
    assert len(engine.history()) == 1


def test_co_training_cycle_runs(seeded) -> None:
    model = NumpyLinearModel(input_dim=6, hidden_dim=14, output_dim=3)
    labeled_x, labeled_y = _make_dataset(n=24, in_dim=6, classes=3)
    unlabeled_x = np.random.randn(50, 6).astype(np.float32)

    engine = SelfTrainingEngine(
        strategy=SelfTrainingStrategy.CO_TRAINING,
        confidence_threshold=0.0,
        gaussian_std=0.02,
        learning_rate=0.003,
    )
    engine.initialize(model)

    batch = engine.train_cycle(labeled_x, labeled_y, unlabeled_x, epochs=2)
    assert batch.sample_count > 0
    assert 0.0 <= batch.avg_confidence <= 1.0


def test_input_validation_blocks_bad_inputs(seeded) -> None:
    model = NumpyLinearModel(input_dim=6, hidden_dim=10, output_dim=3)
    engine = SelfTrainingEngine(strategy=SelfTrainingStrategy.PSEUDO_LABEL, confidence_threshold=0.5)
    engine.initialize(model)

    bad_x = np.random.randn(5, 4).astype(np.float32)
    with pytest.raises(ValueError):
        engine.generate_pseudo_labels(bad_x)

    labeled_x, labeled_y = _make_dataset(n=8, in_dim=6, classes=3)
    unlabeled_x = np.random.randn(10, 6).astype(np.float32)
    with pytest.raises(ValueError):
        engine.train_cycle(labeled_x, labeled_y[:-1], unlabeled_x, epochs=1)
