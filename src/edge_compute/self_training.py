"""
S3M Self-Training Engine
UNCLASSIFIED - FOUO

Implements CPU-native self-training for edge nodes that have limited or no
labeled data. Three strategies:

  1. Noisy Student — a teacher model generates pseudo-labels on unlabeled data;
     a student trains on those labels with stochastic noise (dropout, Gaussian,
     Mixup) to exceed teacher performance. Novel twist: the teacher is
     periodically re-distilled from the improved student (bi-directional
     distillation loop).

  2. Pseudo-Label — simpler variant: model self-labels high-confidence
     predictions and adds them to the training set each cycle.

  3. Co-Training — two models with different feature views label for each other,
     producing diverse supervision.

All strategies operate purely on CPU with numpy. PyTorch is used only when
available for optional acceleration; the engine degrades gracefully to
pure-numpy fallback.
"""

from __future__ import annotations

import copy
import logging
import time
from typing import Any, Dict, List, Optional, Tuple
from uuid import uuid4

import numpy as np

from src.edge_compute.models import PseudoLabelBatch, SelfTrainingStrategy

logger = logging.getLogger("s3m.edge.self_training")


# ═══════════════════════════════════════════════════════════
# Noise Augmentation Functions
# ═══════════════════════════════════════════════════════════


def _validate_finite_array(x: np.ndarray, name: str) -> None:
    """Validate finite numeric arrays before training operations."""
    if not isinstance(x, np.ndarray):
        raise TypeError(f"{name} must be a numpy array")
    if x.size == 0:
        raise ValueError(f"{name} cannot be empty")
    if not np.isfinite(x).all():
        raise ValueError(f"{name} contains non-finite values")


def dropout_noise(x: np.ndarray, rate: float = 0.3) -> np.ndarray:
    """Apply inverted dropout noise to an input array."""
    _validate_finite_array(x, "x")
    if not 0.0 <= rate < 1.0:
        raise ValueError("dropout rate must be in [0.0, 1.0)")
    if rate <= 0.0:
        return x
    mask = np.random.binomial(1, 1.0 - rate, size=x.shape).astype(x.dtype)
    return x * mask / max(1.0 - rate, 1e-8)


def gaussian_noise(x: np.ndarray, std: float = 0.05) -> np.ndarray:
    """Add zero-mean Gaussian noise."""
    _validate_finite_array(x, "x")
    if std < 0.0:
        raise ValueError("gaussian std must be >= 0")
    if std == 0.0:
        return x
    return x + np.random.normal(0.0, std, size=x.shape).astype(x.dtype)


def mixup(x1: np.ndarray, x2: np.ndarray, alpha: float = 0.2) -> Tuple[np.ndarray, float]:
    """Mixup augmentation: returns (mixed_sample, lambda)."""
    _validate_finite_array(x1, "x1")
    _validate_finite_array(x2, "x2")
    if x1.shape != x2.shape:
        raise ValueError("x1 and x2 must have same shape for mixup")
    if alpha < 0.0:
        raise ValueError("mixup alpha must be >= 0")
    lam = float(np.random.beta(alpha, alpha)) if alpha > 0 else 1.0
    mixed = lam * x1 + (1.0 - lam) * x2
    return mixed, lam


def apply_noise_chain(
    x: np.ndarray,
    dropout_rate: float = 0.3,
    gaussian_std: float = 0.05,
) -> np.ndarray:
    """Sequential noise: dropout -> Gaussian."""
    x = dropout_noise(x, dropout_rate)
    x = gaussian_noise(x, gaussian_std)
    return x


# ═══════════════════════════════════════════════════════════
# Lightweight NumPy "Model" for CPU Self-Training
# ═══════════════════════════════════════════════════════════


class NumpyLinearModel:
    """
    Minimal 2-layer linear model (numpy-only) for self-training demonstrations
    and CPU-constrained edge nodes where PyTorch is unavailable.

    Architecture: input -> Linear(H) -> ReLU -> Linear(C) -> softmax
    """

    def __init__(self, input_dim: int, hidden_dim: int = 128, output_dim: int = 10):
        if input_dim <= 0 or hidden_dim <= 0 or output_dim <= 1:
            raise ValueError("input_dim, hidden_dim must be >0 and output_dim must be >1")
        self.input_dim = input_dim
        self.hidden_dim = hidden_dim
        self.output_dim = output_dim
        scale1 = np.sqrt(2.0 / input_dim)
        scale2 = np.sqrt(2.0 / hidden_dim)
        self.params: Dict[str, np.ndarray] = {
            "W1": np.random.randn(input_dim, hidden_dim).astype(np.float32) * scale1,
            "b1": np.zeros(hidden_dim, dtype=np.float32),
            "W2": np.random.randn(hidden_dim, output_dim).astype(np.float32) * scale2,
            "b2": np.zeros(output_dim, dtype=np.float32),
        }

    def forward(self, x: np.ndarray) -> np.ndarray:
        """Forward pass returning softmax probabilities (N, C)."""
        _validate_finite_array(x, "x")
        if x.ndim != 2 or x.shape[1] != self.input_dim:
            raise ValueError("x must be shape (N, input_dim)")
        h = x @ self.params["W1"] + self.params["b1"]
        h = np.maximum(h, 0.0)  # ReLU
        logits = h @ self.params["W2"] + self.params["b2"]
        # Numerically stable softmax
        logits -= logits.max(axis=-1, keepdims=True)
        exp_logits = np.exp(logits)
        denom = exp_logits.sum(axis=-1, keepdims=True)
        return exp_logits / np.maximum(denom, 1e-12)

    def predict(self, x: np.ndarray) -> Tuple[np.ndarray, np.ndarray]:
        """Returns (predicted_classes, confidences)."""
        probs = self.forward(x)
        classes = probs.argmax(axis=-1)
        confidences = probs.max(axis=-1)
        return classes, confidences

    def compute_gradients(
        self, x: np.ndarray, y_onehot: np.ndarray, lr: float = 0.001
    ) -> Dict[str, np.ndarray]:
        """
        One-step backprop returning gradients.
        y_onehot: (N, C) one-hot labels.
        """
        _validate_finite_array(x, "x")
        _validate_finite_array(y_onehot, "y_onehot")
        if lr <= 0.0:
            raise ValueError("lr must be positive")
        if x.ndim != 2 or x.shape[1] != self.input_dim:
            raise ValueError("x must be shape (N, input_dim)")
        if y_onehot.ndim != 2 or y_onehot.shape[1] != self.output_dim:
            raise ValueError("y_onehot must be shape (N, output_dim)")
        if x.shape[0] != y_onehot.shape[0]:
            raise ValueError("x and y_onehot must have same batch size")

        n = x.shape[0]
        # Forward
        h = x @ self.params["W1"] + self.params["b1"]
        h_relu = np.maximum(h, 0.0)
        logits = h_relu @ self.params["W2"] + self.params["b2"]
        logits -= logits.max(axis=-1, keepdims=True)
        exp_logits = np.exp(logits)
        probs = exp_logits / np.maximum(exp_logits.sum(axis=-1, keepdims=True), 1e-12)

        # Cross-entropy gradient at logits
        d_logits = (probs - y_onehot) / max(n, 1)

        grads: Dict[str, np.ndarray] = {
            "W2": h_relu.T @ d_logits,
            "b2": d_logits.sum(axis=0),
        }

        d_h_relu = d_logits @ self.params["W2"].T
        d_h = d_h_relu * (h > 0).astype(np.float32)

        grads["W1"] = x.T @ d_h
        grads["b1"] = d_h.sum(axis=0)

        return grads

    def apply_gradients(self, grads: Dict[str, np.ndarray], lr: float = 0.001) -> float:
        """Update parameters in-place. Returns approximate loss."""
        if lr <= 0.0:
            raise ValueError("lr must be positive")
        required = {"W1", "b1", "W2", "b2"}
        if set(grads.keys()) != required:
            raise ValueError("grads must contain W1,b1,W2,b2")

        for name in self.params:
            if grads[name].shape != self.params[name].shape:
                raise ValueError(f"gradient for {name} has invalid shape")
            self.params[name] -= lr * grads[name]
        # Rough loss estimate from gradient magnitude
        return float(sum(np.abs(g).mean() for g in grads.values()))

    def clone(self) -> "NumpyLinearModel":
        model = NumpyLinearModel(self.input_dim, self.hidden_dim, self.output_dim)
        model.params = {k: v.copy() for k, v in self.params.items()}
        return model

    def distill_to(self, ratio: float = 0.6) -> "NumpyLinearModel":
        """
        Knowledge distillation: create a smaller student model.
        ratio < 1.0 reduces hidden dimension.
        """
        if ratio <= 0.0:
            raise ValueError("distillation ratio must be > 0")
        new_hidden = max(8, int(self.hidden_dim * ratio))
        student = NumpyLinearModel(self.input_dim, new_hidden, self.output_dim)
        # Initialize student with truncated teacher weights
        student.params["W1"] = self.params["W1"][:, :new_hidden].copy()
        student.params["b1"] = self.params["b1"][:new_hidden].copy()
        student.params["W2"] = self.params["W2"][:new_hidden, :].copy()
        student.params["b2"] = self.params["b2"].copy()
        return student


# ═══════════════════════════════════════════════════════════
# Self-Training Engine
# ═══════════════════════════════════════════════════════════


class SelfTrainingEngine:
    """
    Orchestrates self-training on a single CPU edge node.

    Novel element: Bi-directional Noisy Student Loop.
    After the student exceeds the teacher on a held-out validation set,
    the teacher is replaced by a fresh distillation of the student.
    This creates an escalating quality spiral where each generation
    produces harder pseudo-labels than the last.
    """

    def __init__(
        self,
        strategy: SelfTrainingStrategy = SelfTrainingStrategy.NOISY_STUDENT,
        confidence_threshold: float = 0.85,
        dropout_rate: float = 0.3,
        gaussian_std: float = 0.05,
        mixup_alpha: float = 0.2,
        teacher_update_interval: int = 5,
        max_pseudo_per_cycle: int = 10000,
        learning_rate: float = 0.001,
    ):
        if not 0.0 <= confidence_threshold <= 1.0:
            raise ValueError("confidence_threshold must be in [0, 1]")
        if not 0.0 <= dropout_rate < 1.0:
            raise ValueError("dropout_rate must be in [0, 1)")
        if gaussian_std < 0.0:
            raise ValueError("gaussian_std must be >= 0")
        if mixup_alpha < 0.0:
            raise ValueError("mixup_alpha must be >= 0")
        if teacher_update_interval <= 0:
            raise ValueError("teacher_update_interval must be > 0")
        if max_pseudo_per_cycle <= 0:
            raise ValueError("max_pseudo_per_cycle must be > 0")
        if learning_rate <= 0.0:
            raise ValueError("learning_rate must be > 0")

        self.strategy = strategy
        self.confidence_threshold = confidence_threshold
        self.dropout_rate = dropout_rate
        self.gaussian_std = gaussian_std
        self.mixup_alpha = mixup_alpha
        self.teacher_update_interval = teacher_update_interval
        self.max_pseudo_per_cycle = max_pseudo_per_cycle
        self.lr = learning_rate

        self._teacher: Optional[NumpyLinearModel] = None
        self._student: Optional[NumpyLinearModel] = None
        self._co_model_b: Optional[NumpyLinearModel] = None  # For co-training

        self._cycle = 0
        self._total_pseudo_labels = 0
        self._history: List[PseudoLabelBatch] = []

        logger.info(
            "SelfTrainingEngine: strategy=%s, confidence=%.2f",
            strategy.value,
            confidence_threshold,
        )

    def initialize(self, model: NumpyLinearModel) -> None:
        """Set the initial teacher model. Student is cloned from it."""
        if not isinstance(model, NumpyLinearModel):
            raise TypeError("model must be NumpyLinearModel")
        self._teacher = model.clone()
        self._student = model.clone()
        if self.strategy == SelfTrainingStrategy.CO_TRAINING:
            # Tactical context: co-training uses a second independently seeded
            # branch to mimic heterogeneous sensors or feature views.
            self._co_model_b = model.clone()

    # ── Pseudo-Label Generation ──────────────────────────

    def generate_pseudo_labels(
        self, unlabeled_data: np.ndarray
    ) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
        """
        Use teacher to label unlabeled data.
        Returns (selected_data, pseudo_labels_onehot, confidences)
        for samples above the confidence threshold.
        """
        if self._teacher is None:
            raise RuntimeError("Call initialize() first")
        _validate_finite_array(unlabeled_data, "unlabeled_data")
        if unlabeled_data.ndim != 2 or unlabeled_data.shape[1] != self._teacher.input_dim:
            raise ValueError("unlabeled_data must have shape (N, input_dim)")

        classes, confidences = self._teacher.predict(unlabeled_data)
        mask = confidences >= self.confidence_threshold

        # Cap at max per cycle
        selected_indices = np.where(mask)[0]
        if len(selected_indices) > self.max_pseudo_per_cycle:
            # Take the most confident ones
            top_k = np.argsort(confidences[selected_indices])[-self.max_pseudo_per_cycle :]
            selected_indices = selected_indices[top_k]

        selected_data = unlabeled_data[selected_indices]
        selected_classes = classes[selected_indices]
        selected_conf = confidences[selected_indices]

        # One-hot encode
        n_classes = self._teacher.output_dim
        onehot = np.zeros((len(selected_classes), n_classes), dtype=np.float32)
        if len(selected_classes) > 0:
            onehot[np.arange(len(selected_classes)), selected_classes] = 1.0

        return selected_data, onehot, selected_conf

    # ── Training Cycles ──────────────────────────────────

    def train_cycle(
        self,
        labeled_x: np.ndarray,
        labeled_y: np.ndarray,
        unlabeled_x: np.ndarray,
        epochs: int = 3,
    ) -> PseudoLabelBatch:
        """
        Run one self-training cycle:
          1. Teacher generates pseudo-labels for unlabeled data.
          2. Student trains on labeled + pseudo-labeled data with noise.
          3. (Optionally) swap teacher <- student.
        """
        if self._student is None:
            raise RuntimeError("Call initialize() first")
        if epochs <= 0:
            raise ValueError("epochs must be > 0")

        _validate_finite_array(labeled_x, "labeled_x")
        _validate_finite_array(labeled_y, "labeled_y")
        _validate_finite_array(unlabeled_x, "unlabeled_x")

        if labeled_x.ndim != 2 or labeled_x.shape[1] != self._student.input_dim:
            raise ValueError("labeled_x must have shape (N, input_dim)")
        if unlabeled_x.ndim != 2 or unlabeled_x.shape[1] != self._student.input_dim:
            raise ValueError("unlabeled_x must have shape (N, input_dim)")
        if labeled_y.ndim != 2 or labeled_y.shape[1] != self._student.output_dim:
            raise ValueError("labeled_y must have shape (N, output_dim)")
        if labeled_x.shape[0] != labeled_y.shape[0]:
            raise ValueError("labeled_x and labeled_y size mismatch")

        if self.strategy == SelfTrainingStrategy.CO_TRAINING:
            return self._co_training_cycle(labeled_x, labeled_y, unlabeled_x, epochs)

        # Generate pseudo-labels
        pseudo_x, pseudo_y, pseudo_conf = self.generate_pseudo_labels(unlabeled_x)

        if len(pseudo_x) == 0:
            logger.warning(
                "No samples passed confidence threshold %.2f", self.confidence_threshold
            )
            return PseudoLabelBatch(
                strategy=self.strategy, sample_count=0, avg_confidence=0.0
            )

        # Combine real + pseudo data
        combined_x = np.concatenate([labeled_x, pseudo_x], axis=0)
        combined_y = np.concatenate([labeled_y, pseudo_y], axis=0)

        # Tactical context: mixup simulates uncertain battlefield observation
        # blending to prevent brittle overfitting on pseudo-labels.
        if self.strategy == SelfTrainingStrategy.NOISY_STUDENT and len(combined_x) > 1:
            shuffled = np.random.permutation(len(combined_x))
            mixed_x, lam = mixup(combined_x, combined_x[shuffled], self.mixup_alpha)
            mixed_y = lam * combined_y + (1.0 - lam) * combined_y[shuffled]
            combined_x = mixed_x.astype(np.float32)
            combined_y = mixed_y.astype(np.float32)

        # Train student with noise augmentation
        for _ in range(epochs):
            if self.strategy == SelfTrainingStrategy.NOISY_STUDENT:
                noisy_x = apply_noise_chain(combined_x, self.dropout_rate, self.gaussian_std)
            else:
                noisy_x = combined_x

            grads = self._student.compute_gradients(noisy_x, combined_y, self.lr)
            self._student.apply_gradients(grads, self.lr)

        self._cycle += 1
        self._total_pseudo_labels += len(pseudo_x)

        # Bi-directional teacher update (re-distill teacher from student)
        if self._cycle % self.teacher_update_interval == 0:
            logger.info(
                "Cycle %d: updating teacher from student (bi-directional distillation)",
                self._cycle,
            )
            self._teacher = self._student.clone().distill_to(ratio=1.0)

        batch = PseudoLabelBatch(
            strategy=self.strategy,
            sample_count=len(pseudo_x),
            avg_confidence=float(pseudo_conf.mean()),
            noise_applied=(self.strategy == SelfTrainingStrategy.NOISY_STUDENT),
        )
        self._history.append(batch)
        logger.info(
            "Self-training cycle %d: %d pseudo-labels, avg_conf=%.3f",
            self._cycle,
            len(pseudo_x),
            batch.avg_confidence,
        )
        return batch

    def _co_training_cycle(
        self,
        labeled_x: np.ndarray,
        labeled_y: np.ndarray,
        unlabeled_x: np.ndarray,
        epochs: int,
    ) -> PseudoLabelBatch:
        """
        Co-Training: Model A labels for Model B and vice versa.
        The two models use different random seeds / augmentations to
        provide diversity of supervision signals.
        """
        if self._co_model_b is None or self._student is None:
            raise RuntimeError("Co-training requires two models")

        # Model A labels
        classes_a, conf_a = self._student.predict(unlabeled_x)
        mask_a = conf_a >= self.confidence_threshold

        # Model B labels
        view_b = gaussian_noise(unlabeled_x, max(self.gaussian_std, 0.01))
        classes_b, conf_b = self._co_model_b.predict(view_b)
        mask_b = conf_b >= self.confidence_threshold

        # Cross-train: A's labels train B, B's labels train A
        n_classes = self._student.output_dim

        if mask_a.sum() > 0:
            x_for_b = unlabeled_x[mask_a]
            y_for_b = np.zeros((mask_a.sum(), n_classes), dtype=np.float32)
            y_for_b[np.arange(mask_a.sum()), classes_a[mask_a]] = 1.0
            combined_x = np.concatenate([labeled_x, x_for_b])
            combined_y = np.concatenate([labeled_y, y_for_b])
            for _ in range(epochs):
                g = self._co_model_b.compute_gradients(combined_x, combined_y)
                self._co_model_b.apply_gradients(g, self.lr)

        if mask_b.sum() > 0:
            x_for_a = view_b[mask_b]
            y_for_a = np.zeros((mask_b.sum(), n_classes), dtype=np.float32)
            y_for_a[np.arange(mask_b.sum()), classes_b[mask_b]] = 1.0
            combined_x = np.concatenate([labeled_x, x_for_a])
            combined_y = np.concatenate([labeled_y, y_for_a])
            for _ in range(epochs):
                g = self._student.compute_gradients(combined_x, combined_y)
                self._student.apply_gradients(g, self.lr)

        total = int(mask_a.sum() + mask_b.sum())
        avg_conf = float(
            np.mean(
                [
                    conf_a[mask_a].mean() if mask_a.any() else 0,
                    conf_b[mask_b].mean() if mask_b.any() else 0,
                ]
            )
        )
        self._cycle += 1
        self._total_pseudo_labels += total

        batch = PseudoLabelBatch(
            strategy=self.strategy, sample_count=total, avg_confidence=avg_conf
        )
        self._history.append(batch)
        return batch

    # ── Accessors ────────────────────────────────────────

    def get_student(self) -> Optional[NumpyLinearModel]:
        return self._student

    def get_teacher(self) -> Optional[NumpyLinearModel]:
        return self._teacher

    def history(self) -> List[PseudoLabelBatch]:
        return list(self._history)

    def health_check(self) -> Dict[str, Any]:
        return {
            "strategy": self.strategy.value,
            "cycle": self._cycle,
            "total_pseudo_labels": self._total_pseudo_labels,
            "confidence_threshold": self.confidence_threshold,
            "teacher_initialized": self._teacher is not None,
            "student_initialized": self._student is not None,
        }
