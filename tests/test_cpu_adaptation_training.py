"""Unit tests for CPU adaptation training utilities."""

from __future__ import annotations

import numpy as np
import pytest
import torch

from src.training.cpu_adaptation.adapter_tuner import AdapterConfig, CPUAdapterTuner, TrainingResult
from src.training.cpu_adaptation.classifier_retrainer import ClassifierConfig, ClassifierRetrainer
from src.training.cpu_adaptation.distillation_engine import DistillationEngine
from src.training.cpu_adaptation.federated_aggregator import FederatedAggregator


def test_federated_aggregator_fedavg_with_partial_updates() -> None:
    aggregator = FederatedAggregator("fedavg")
    aggregator.register_update("node-1", {"layer.a": torch.tensor([1.0, 2.0]), "layer.b": [5.0]}, n_samples=10)
    aggregator.register_update("node-2", {"layer.a": torch.tensor([3.0, 4.0])}, n_samples=30)

    merged = aggregator.aggregate()
    assert set(merged.keys()) == {"layer.a", "layer.b"}
    assert torch.allclose(merged["layer.a"], torch.tensor([2.5, 3.5]), atol=1e-6)
    assert torch.allclose(merged["layer.b"], torch.tensor([5.0]), atol=1e-6)


def test_federated_aggregator_trimmed_mean_reduces_outlier() -> None:
    aggregator = FederatedAggregator("trimmed_mean")
    values = [1.0, 1.1, 0.9, 1.0, 50.0]
    for idx, value in enumerate(values):
        aggregator.register_update(f"node-{idx}", {"layer.a": [value]}, n_samples=10)
    merged = aggregator.aggregate()
    assert merged["layer.a"].item() < 2.0


def test_classifier_retrainer_mlp_torch_train_predict_export(tmp_path) -> None:
    rng = np.random.default_rng(42)
    X = rng.normal(size=(64, 6)).astype(np.float32)
    y = np.argmax(
        np.stack(
            [
                X[:, 0] + 0.25 * X[:, 1],
                -X[:, 2] + 0.3 * X[:, 3],
                X[:, 4] - X[:, 5],
            ],
            axis=1,
        ),
        axis=1,
    ).astype(np.int64)

    retrainer = ClassifierRetrainer("mlp_torch", ClassifierConfig(n_classes=3, feature_dim=6, max_train_time_sec=10))
    result = retrainer.train(X, y)
    preds = retrainer.predict(X)
    path = retrainer.export(str(tmp_path / "mlp.joblib"))

    assert 0.0 <= result.accuracy <= 1.0
    assert 0.0 <= result.f1_weighted <= 1.0
    assert preds.shape == (64,)
    assert path.endswith(".joblib")


def test_classifier_retrainer_validates_inputs() -> None:
    retrainer = ClassifierRetrainer("mlp_torch", ClassifierConfig(n_classes=2, feature_dim=4))
    X = np.ones((5, 3), dtype=np.float32)
    y = np.zeros((5,), dtype=np.int64)
    with pytest.raises(ValueError):
        retrainer.train(X, y)


def test_adapter_tuner_enforces_memory_budget(monkeypatch) -> None:
    tuner = CPUAdapterTuner("dummy-base", AdapterConfig(max_memory_mb=1))
    monkeypatch.setattr(tuner, "_current_rss_mb", lambda: 2.5)
    with pytest.raises(MemoryError):
        tuner._enforce_memory_budget()


def test_distillation_engine_uses_cpu_adapter_tuner(monkeypatch, tmp_path) -> None:
    class FakeTeacher:
        def generate(self, prompt: str, **kwargs):  # noqa: ANN001
            _ = kwargs
            return {"response": f"teacher::{prompt}"}

    class FakeTuner:
        def __init__(self, base_model_path: str, adapter_config: AdapterConfig):
            self.base_model_path = base_model_path
            self.adapter_config = adapter_config

        def prepare(self) -> bool:
            return True

        def train(self, dataset):  # noqa: ANN001
            _ = dataset
            return TrainingResult(
                loss_history=[0.5, 0.4],
                steps_completed=2,
                peak_memory_mb=512.0,
                duration_seconds=0.1,
                adapter_path="adapter-dir",
            )

        def merge_and_quantize(self, output_path: str, quant_format: str = "q4_k_m") -> str:
            _ = quant_format
            return str(output_path)

        def export_adapter(self, output_path: str) -> str:
            return str(output_path)

    import src.training.cpu_adaptation.distillation_engine as de

    monkeypatch.setattr(de, "CPUAdapterTuner", FakeTuner)

    engine = DistillationEngine(
        teacher_backend=FakeTeacher(),
        student_config={"base_model_path": "student-base", "merge_and_quantize": True},
    )
    training_data = engine.generate_training_data(["secure route", "radar check"], max_samples=2)
    result = engine.distill(training_data, str(tmp_path / "student.gguf"))

    assert len(training_data) == 2
    assert result.samples_used == 2
    assert result.student_path.endswith("student.gguf")
    assert 0.0 <= result.teacher_agreement_pct <= 100.0
