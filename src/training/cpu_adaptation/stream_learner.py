"""Streaming learner for on-node adaptation in austere tactical settings."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Optional, Sequence

import numpy as np


@dataclass(frozen=True)
class StreamUpdate:
    """Single online update record used for mission-audit traceability."""

    prediction: float
    target: float
    error: float
    samples_seen: int


class StreamLearner:
    """
    Lightweight online linear learner for edge adaptation.

    This model intentionally uses CPU-safe operations only, enabling continuous
    adaptation when GPU acceleration is unavailable in field operations.
    """

    def __init__(
        self,
        learning_rate: float = 0.05,
        feature_dim: Optional[int] = None,
    ) -> None:
        if learning_rate <= 0.0 or learning_rate > 1.0:
            raise ValueError("learning_rate must be in (0.0, 1.0]")
        if feature_dim is not None and feature_dim <= 0:
            raise ValueError("feature_dim must be > 0")
        self.learning_rate = float(learning_rate)
        self.feature_dim = int(feature_dim) if feature_dim is not None else None
        self.weights: Optional[np.ndarray] = None
        self.bias: float = 0.0
        self.samples_seen: int = 0

    def partial_fit(self, features: Sequence[float], target: float) -> StreamUpdate:
        vector = self._validate_vector(features)
        if self.weights is None:
            self.weights = np.zeros(vector.shape[0], dtype=np.float64)
            self.feature_dim = int(vector.shape[0])

        prediction = float(np.dot(self.weights, vector) + self.bias)
        error = float(target) - prediction
        # Tactical context: conservative SGD update avoids unstable drift in live missions.
        self.weights = self.weights + (self.learning_rate * error * vector)
        self.bias += self.learning_rate * error
        self.samples_seen += 1
        return StreamUpdate(
            prediction=prediction,
            target=float(target),
            error=error,
            samples_seen=self.samples_seen,
        )

    def predict(self, features: Sequence[float]) -> float:
        vector = self._validate_vector(features)
        if self.weights is None:
            return 0.0
        return float(np.dot(self.weights, vector) + self.bias)

    def state_dict(self) -> Dict[str, object]:
        return {
            "learning_rate": self.learning_rate,
            "feature_dim": self.feature_dim,
            "weights": None if self.weights is None else self.weights.tolist(),
            "bias": self.bias,
            "samples_seen": self.samples_seen,
        }

    def _validate_vector(self, features: Sequence[float]) -> np.ndarray:
        vector = np.asarray(features, dtype=np.float64).reshape(-1)
        if vector.size == 0:
            raise ValueError("features must contain at least one value")
        if self.feature_dim is not None and int(vector.shape[0]) != int(self.feature_dim):
            raise ValueError(
                f"feature length mismatch: expected {self.feature_dim}, got {vector.shape[0]}"
            )
        return vector
