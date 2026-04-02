"""
S3M Self-Growth Engine
UNCLASSIFIED - FOUO

Implements dynamic model expansion for tactical edge nodes where loss plateaus
may indicate that additional representational capacity is required.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any, Callable, Dict, List, Optional

import numpy as np


@dataclass
class PlateauDetector:
    """Detects stalled validation loss improvements over consecutive cycles."""

    patience: int = 3
    min_delta: float = 0.01

    def __post_init__(self) -> None:
        if self.patience <= 0:
            raise ValueError("patience must be > 0")
        if self.min_delta < 0.0:
            raise ValueError("min_delta must be >= 0")
        self._best_value: Optional[float] = None
        self._stall_count: int = 0

    def record(self, metric_value: float) -> bool:
        """
        Record a new metric value.
        Returns True when a plateau is detected.
        """
        value = float(metric_value)
        if self._best_value is None:
            self._best_value = value
            self._stall_count = 0
            return False

        # Tactical context: for loss metrics, only meaningful improvement
        # above min_delta resets stall state.
        if (self._best_value - value) > self.min_delta:
            self._best_value = value
            self._stall_count = 0
            return False

        self._stall_count += 1
        return self._stall_count >= self.patience

    def reset(self) -> None:
        self._best_value = None
        self._stall_count = 0


class GrowableModel:
    """
    Lightweight NumPy MLP with dynamic depth and width growth.
    Hidden layers use ReLU activations; output uses softmax.
    """

    def __init__(
        self,
        input_dim: int,
        hidden_dim: int,
        output_dim: int,
        n_hidden_layers: int = 2,
    ):
        if input_dim <= 0 or hidden_dim <= 0 or output_dim <= 1:
            raise ValueError("input_dim/hidden_dim must be >0 and output_dim >1")
        if n_hidden_layers <= 0:
            raise ValueError("n_hidden_layers must be > 0")

        self.input_dim = int(input_dim)
        self.hidden_dim = int(hidden_dim)
        self.output_dim = int(output_dim)

        self._weights: List[np.ndarray] = []
        self._biases: List[np.ndarray] = []
        self._init_topology(n_hidden_layers=n_hidden_layers)

    def _init_topology(self, n_hidden_layers: int) -> None:
        self._weights = []
        self._biases = []

        # Input -> first hidden
        self._weights.append(
            (np.random.randn(self.input_dim, self.hidden_dim).astype(np.float32))
            * np.sqrt(2.0 / self.input_dim)
        )
        self._biases.append(np.zeros(self.hidden_dim, dtype=np.float32))

        # Hidden -> hidden
        for _ in range(max(0, n_hidden_layers - 1)):
            self._weights.append(
                (np.random.randn(self.hidden_dim, self.hidden_dim).astype(np.float32))
                * np.sqrt(2.0 / self.hidden_dim)
            )
            self._biases.append(np.zeros(self.hidden_dim, dtype=np.float32))

        # Final hidden -> output
        self._weights.append(
            (np.random.randn(self.hidden_dim, self.output_dim).astype(np.float32))
            * np.sqrt(2.0 / self.hidden_dim)
        )
        self._biases.append(np.zeros(self.output_dim, dtype=np.float32))

    @property
    def n_layers(self) -> int:
        """Total layer count including output layer."""
        return len(self._weights)

    @property
    def memory_mb(self) -> float:
        total_bytes = sum(w.nbytes for w in self._weights) + sum(b.nbytes for b in self._biases)
        return float(total_bytes) / (1024.0 * 1024.0)

    def forward(self, x: np.ndarray) -> np.ndarray:
        if not isinstance(x, np.ndarray):
            raise TypeError("x must be numpy.ndarray")
        if x.ndim != 2 or x.shape[1] != self.input_dim:
            raise ValueError("x must have shape (N, input_dim)")
        if not np.isfinite(x).all():
            raise ValueError("x must contain only finite values")

        h = x.astype(np.float32, copy=False)
        for i in range(self.n_layers - 1):
            h = h @ self._weights[i] + self._biases[i]
            h = np.maximum(h, 0.0)
        logits = h @ self._weights[-1] + self._biases[-1]
        logits = logits - logits.max(axis=-1, keepdims=True)
        exp_logits = np.exp(logits)
        return exp_logits / np.maximum(exp_logits.sum(axis=-1, keepdims=True), 1e-12)

    def grow(self, n_new_layers: int = 1, perturbation_scale: float = 0.01) -> Dict[str, Any]:
        """
        Add hidden->hidden layers before output.
        New layers are initialized near-identity to preserve behavior.
        """
        if n_new_layers <= 0:
            raise ValueError("n_new_layers must be > 0")
        if perturbation_scale < 0.0:
            raise ValueError("perturbation_scale must be >= 0")

        for _ in range(n_new_layers):
            identity = np.eye(self.hidden_dim, dtype=np.float32)
            if perturbation_scale > 0.0:
                identity = identity + np.random.normal(
                    loc=0.0,
                    scale=perturbation_scale,
                    size=(self.hidden_dim, self.hidden_dim),
                ).astype(np.float32)
            self._weights.insert(-1, identity)
            self._biases.insert(-1, np.zeros(self.hidden_dim, dtype=np.float32))

        return {
            "layers_added": int(n_new_layers),
            "new_layer_count": self.n_layers,
            "memory_mb": round(self.memory_mb, 6),
            "timestamp": time.time(),
        }

    def widen(self, new_hidden_dim: int) -> Dict[str, Any]:
        """Increase hidden width and preserve overlapping parameters."""
        if new_hidden_dim <= 0:
            raise ValueError("new_hidden_dim must be > 0")

        old_hidden = self.hidden_dim
        if new_hidden_dim == old_hidden:
            return {
                "new_hidden_dim": old_hidden,
                "old_hidden_dim": old_hidden,
                "changed": False,
            }

        old_weights = [w.copy() for w in self._weights]
        old_biases = [b.copy() for b in self._biases]
        n_hidden_layers = self.n_layers - 1

        self.hidden_dim = int(new_hidden_dim)
        self._init_topology(n_hidden_layers=n_hidden_layers)

        overlap = min(old_hidden, new_hidden_dim)

        # Copy overlap for first hidden projection.
        self._weights[0][:, :overlap] = old_weights[0][:, :overlap]
        self._biases[0][:overlap] = old_biases[0][:overlap]

        # Copy overlap for hidden transitions.
        for idx in range(1, n_hidden_layers):
            self._weights[idx][:overlap, :overlap] = old_weights[idx][:overlap, :overlap]
            self._biases[idx][:overlap] = old_biases[idx][:overlap]

        # Copy overlap for output projection.
        self._weights[-1][:overlap, :] = old_weights[-1][:overlap, :]
        self._biases[-1] = old_biases[-1]

        return {
            "new_hidden_dim": int(new_hidden_dim),
            "old_hidden_dim": int(old_hidden),
            "changed": True,
            "memory_mb": round(self.memory_mb, 6),
        }

    def topology(self) -> List[Dict[str, Any]]:
        layout: List[Dict[str, Any]] = []
        for idx in range(self.n_layers):
            if idx < self.n_layers - 1:
                in_dim = self.input_dim if idx == 0 else self.hidden_dim
                out_dim = self.hidden_dim
                layer_type = "hidden"
            else:
                in_dim = self.hidden_dim
                out_dim = self.output_dim
                layer_type = "output"
            layout.append({"index": idx, "type": layer_type, "in": in_dim, "out": out_dim})
        return layout


class SelfGrowthEngine:
    """
    Coordinates growth decisions and bounded expansion for edge models.
    """

    def __init__(
        self,
        patience: int = 3,
        min_delta: float = 0.01,
        max_layers: int = 128,
        max_memory_mb: float = 1024.0,
    ):
        if max_layers <= 1:
            raise ValueError("max_layers must be > 1")
        if max_memory_mb <= 0.0:
            raise ValueError("max_memory_mb must be > 0")

        self.max_layers = int(max_layers)
        self.max_memory_mb = float(max_memory_mb)
        self.plateau_detector = PlateauDetector(patience=patience, min_delta=min_delta)
        self.model: Optional[GrowableModel] = None
        self._growth_events: List[Dict[str, Any]] = []
        self._audit_callback: Optional[Callable[..., None]] = None

    def initialize(
        self,
        input_dim: int,
        hidden_dim: int,
        output_dim: int,
        n_hidden_layers: int = 2,
    ) -> GrowableModel:
        self.model = GrowableModel(input_dim, hidden_dim, output_dim, n_hidden_layers)
        self.plateau_detector.reset()
        return self.model

    def set_audit_callback(self, callback: Callable[..., None]) -> None:
        self._audit_callback = callback

    @staticmethod
    def _cross_entropy(y_true: np.ndarray, probs: np.ndarray) -> float:
        if y_true.shape != probs.shape:
            raise ValueError("y_true and probs must have same shape")
        p = np.clip(probs, 1e-10, 1.0)
        return float(-(y_true * np.log(p)).sum(axis=1).mean())

    def train_cycle(
        self,
        train_x: np.ndarray,
        train_y: np.ndarray,
        val_x: np.ndarray,
        val_y: np.ndarray,
        epochs: int = 1,
        lr: float = 0.01,
    ) -> Dict[str, Any]:
        if self.model is None:
            raise RuntimeError("Call initialize() before train_cycle()")
        if epochs <= 0:
            raise ValueError("epochs must be > 0")
        if lr <= 0:
            raise ValueError("lr must be > 0")

        for arr_name, arr in {
            "train_x": train_x,
            "train_y": train_y,
            "val_x": val_x,
            "val_y": val_y,
        }.items():
            if not isinstance(arr, np.ndarray):
                raise TypeError(f"{arr_name} must be a numpy.ndarray")
            if not np.isfinite(arr).all():
                raise ValueError(f"{arr_name} contains non-finite values")

        for _ in range(epochs):
            # Lightweight output-layer update for fast CPU execution on edge nodes.
            hidden = train_x.astype(np.float32, copy=False)
            for i in range(self.model.n_layers - 1):
                hidden = hidden @ self.model._weights[i] + self.model._biases[i]
                hidden = np.maximum(hidden, 0.0)

            probs = self.model.forward(train_x)
            grad_logits = (probs - train_y) / max(train_x.shape[0], 1)
            grad_w = hidden.T @ grad_logits
            grad_b = grad_logits.sum(axis=0)

            self.model._weights[-1] -= lr * grad_w.astype(np.float32)
            self.model._biases[-1] -= lr * grad_b.astype(np.float32)

        train_probs = self.model.forward(train_x)
        val_probs = self.model.forward(val_x)
        train_loss = self._cross_entropy(train_y, train_probs)
        val_loss = self._cross_entropy(val_y, val_probs)

        plateau = self.plateau_detector.record(val_loss)
        growth_event = None
        if plateau:
            growth_event = self.force_grow(1, reason="plateau_detected")

        return {
            "train_loss": float(train_loss),
            "val_loss": float(val_loss),
            "layers": self.model.n_layers,
            "growth_event": growth_event,
        }

    def force_grow(self, n_new_layers: int = 1, reason: str = "manual") -> Optional[Dict[str, Any]]:
        if self.model is None:
            raise RuntimeError("Call initialize() before force_grow()")
        if n_new_layers <= 0:
            raise ValueError("n_new_layers must be > 0")

        allowed_by_layers = self.max_layers - self.model.n_layers
        if allowed_by_layers <= 0:
            return None

        layers_to_add = min(int(n_new_layers), int(allowed_by_layers))
        add_bytes_per_layer = (
            self.model.hidden_dim * self.model.hidden_dim * 4
            + self.model.hidden_dim * 4
        )
        projected_mb = self.model.memory_mb + (
            (layers_to_add * add_bytes_per_layer) / (1024.0 * 1024.0)
        )
        if projected_mb > self.max_memory_mb:
            return None

        event = self.model.grow(n_new_layers=layers_to_add)
        event["reason"] = reason
        event["action"] = "model_growth"
        self._growth_events.append(event)
        self.plateau_detector.reset()

        if self._audit_callback is not None:
            try:
                self._audit_callback(**event)
            except Exception:
                # Callback failures must not interrupt tactical learning loops.
                pass

        return event

    def health_check(self) -> Dict[str, Any]:
        return {
            "layers": self.model.n_layers if self.model else 0,
            "memory_mb": round(self.model.memory_mb, 6) if self.model else 0.0,
            "growth_events": len(self._growth_events),
            "plateau_detector": {
                "patience": self.plateau_detector.patience,
                "min_delta": self.plateau_detector.min_delta,
                "stall_count": self.plateau_detector._stall_count,
                "best_value": self.plateau_detector._best_value,
            },
        }
