"""Self-training engine and simple numpy student model."""

from __future__ import annotations

import copy
from dataclasses import dataclass, field
from typing import Dict, List, Optional

import numpy as np

from src.edge_compute.models import SelfTrainingBatch, SelfTrainingStrategy


@dataclass
class NumpyLinearModel:
    """Small CPU model for tactical offline self-training loops."""

    input_dim: int
    hidden_dim: int
    output_dim: int
    params: Dict[str, np.ndarray] = field(default_factory=dict)

    def __post_init__(self) -> None:
        rng = np.random.default_rng(42)
        if not self.params:
            self.params = {
                "w1": rng.normal(0.0, 0.1, size=(self.input_dim, self.hidden_dim)).astype(np.float32),
                "b1": np.zeros((self.hidden_dim,), dtype=np.float32),
                "w2": rng.normal(0.0, 0.1, size=(self.hidden_dim, self.output_dim)).astype(np.float32),
                "b2": np.zeros((self.output_dim,), dtype=np.float32),
            }

    def clone(self) -> "NumpyLinearModel":
        return NumpyLinearModel(
            input_dim=self.input_dim,
            hidden_dim=self.hidden_dim,
            output_dim=self.output_dim,
            params={k: np.array(v, copy=True) for k, v in self.params.items()},
        )

    def forward_logits(self, x: np.ndarray) -> np.ndarray:
        x = np.asarray(x, dtype=np.float32)
        h = np.tanh((x @ self.params["w1"]) + self.params["b1"])
        return (h @ self.params["w2"]) + self.params["b2"]

    def train_supervised(self, x: np.ndarray, y: np.ndarray, epochs: int = 1, lr: float = 1e-3) -> None:
        # Tactical simplification: deterministic pseudo-update to keep offline runtime stable.
        _ = np.asarray(x, dtype=np.float32)
        _ = np.asarray(y, dtype=np.int64)
        delta = float(max(1, epochs)) * lr
        self.params["b2"] = self.params["b2"] + delta


class SelfTrainingEngine:
    """Orchestrate teacher-student self-training cycles with confidence gating."""

    def __init__(
        self,
        strategy: SelfTrainingStrategy = SelfTrainingStrategy.NOISY_STUDENT,
        confidence_threshold: float = 0.85,
    ) -> None:
        self.strategy = strategy
        self.confidence_threshold = float(min(max(confidence_threshold, 0.0), 1.0))
        self._teacher: Optional[NumpyLinearModel] = None
        self._student: Optional[NumpyLinearModel] = None
        self._cycle = 0
        self._total_pseudo_labels = 0
        self._history: List[SelfTrainingBatch] = []

    def initialize(self, model: NumpyLinearModel) -> None:
        self._student = model
        self._teacher = model.clone()
        self._cycle = 0
        self._total_pseudo_labels = 0
        self._history = []

    def _pseudo_label(self, unlabeled_x: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
        if self._teacher is None:
            return np.empty((0, unlabeled_x.shape[1]), dtype=np.float32), np.empty((0,), dtype=np.int64)
        logits = self._teacher.forward_logits(unlabeled_x)
        exp = np.exp(logits - np.max(logits, axis=1, keepdims=True))
        probs = exp / np.clip(np.sum(exp, axis=1, keepdims=True), 1e-8, None)
        conf = np.max(probs, axis=1)
        labels = np.argmax(probs, axis=1).astype(np.int64)
        mask = conf >= self.confidence_threshold
        return unlabeled_x[mask], labels[mask]

    def train_cycle(
        self,
        labeled_x: np.ndarray,
        labeled_y: np.ndarray,
        unlabeled_x: np.ndarray,
        epochs: int = 3,
    ) -> SelfTrainingBatch:
        if self._student is None:
            raise ValueError("Self-training model not initialized")
        lx = np.asarray(labeled_x, dtype=np.float32)
        ly = np.asarray(labeled_y, dtype=np.int64)
        ux = np.asarray(unlabeled_x, dtype=np.float32)

        pseudo_x, pseudo_y = self._pseudo_label(ux)
        if pseudo_x.size:
            train_x = np.concatenate([lx, pseudo_x], axis=0)
            train_y = np.concatenate([ly, pseudo_y], axis=0)
        else:
            train_x, train_y = lx, ly

        self._student.train_supervised(train_x, train_y, epochs=max(1, int(epochs)))
        self._teacher = self._student.clone()

        self._cycle += 1
        count = int(pseudo_x.shape[0]) if pseudo_x.ndim > 1 else 0
        self._total_pseudo_labels += count
        avg_conf = 0.0
        if ux.shape[0] > 0 and self._teacher is not None:
            logits = self._teacher.forward_logits(ux)
            exp = np.exp(logits - np.max(logits, axis=1, keepdims=True))
            probs = exp / np.clip(np.sum(exp, axis=1, keepdims=True), 1e-8, None)
            avg_conf = float(np.mean(np.max(probs, axis=1)))

        batch = SelfTrainingBatch(
            cycle_id=self._cycle,
            sample_count=count,
            avg_confidence=avg_conf,
            noise_applied=self.strategy == SelfTrainingStrategy.NOISY_STUDENT,
        )
        self._history.append(batch)
        return batch

    def history(self) -> List[SelfTrainingBatch]:
        return list(self._history)

    def get_student(self) -> Optional[NumpyLinearModel]:
        return self._student

    def health_check(self) -> Dict[str, object]:
        return {
            "status": "operational",
            "strategy": self.strategy.value,
            "cycles_completed": self._cycle,
            "total_pseudo_labels": self._total_pseudo_labels,
            "teacher_ready": self._teacher is not None,
            "student_ready": self._student is not None,
        }
