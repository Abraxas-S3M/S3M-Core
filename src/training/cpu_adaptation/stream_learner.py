"""Streaming learner for on-node adaptation in austere tactical settings."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional, Sequence

import numpy as np


_FLEET_MAINTENANCE_LOG = Path("data/training/fleet_maintenance.jsonl")
_EMBEDDING_STREAM_LOG = Path("data/training/embedding_stream.jsonl")


def log_fleet_maintenance_training_sample(
    fleet_health: Optional[Dict[str, Any]] = None,
    maintenance_outcomes: Optional[Sequence[Dict[str, Any]]] = None,
    output_path: Optional[Path] = None,
) -> Dict[str, Any]:
    """
    Append one sustainment training sample for CPU adaptation.

    Tactical context: field snapshots of fleet readiness and maintenance outcomes
    are preserved as local JSONL so edge-only adaptation can continue without
    external service dependencies.
    """

    if fleet_health is not None and not isinstance(fleet_health, dict):
        raise ValueError("fleet_health must be a dictionary when provided")

    normalized_outcomes: list[Dict[str, Any]] = []
    if maintenance_outcomes is not None:
        if isinstance(maintenance_outcomes, (str, bytes)):
            raise ValueError("maintenance_outcomes must be a sequence of dictionaries")
        for outcome in maintenance_outcomes:
            if not isinstance(outcome, dict):
                raise ValueError("each maintenance outcome must be a dictionary")
            normalized_outcomes.append(dict(outcome))

    payload = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "fleetHealth": dict(fleet_health or {}),
        "maintenanceOutcomes": normalized_outcomes,
    }
    target = output_path or _FLEET_MAINTENANCE_LOG
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload, default=str))
        handle.write("\n")
    return payload


def log_embedding_training_sample(
    sample_id: str,
    embedding: Sequence[float],
    metadata: Optional[Dict[str, Any]] = None,
    output_path: Optional[Path] = None,
) -> Dict[str, Any]:
    """
    Append one semantic embedding sample for CPU adaptation.

    Tactical context: every semantic retrieval vector and its mission metadata is
    captured locally so adaptation pipelines can learn from field observations.
    """
    if not isinstance(sample_id, str) or not sample_id.strip():
        raise ValueError("sample_id must be a non-empty string")
    if not isinstance(embedding, Sequence) or isinstance(embedding, (str, bytes)):
        raise ValueError("embedding must be a numeric sequence")
    vector = np.asarray(embedding, dtype=np.float32).reshape(-1)
    if vector.size == 0:
        raise ValueError("embedding must contain at least one value")
    if metadata is not None and not isinstance(metadata, dict):
        raise ValueError("metadata must be a dictionary when provided")

    payload = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "sampleId": sample_id.strip(),
        "embedding": vector.tolist(),
        "metadata": dict(metadata or {}),
    }
    target = output_path or _EMBEDDING_STREAM_LOG
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload, default=str))
        handle.write("\n")
    return payload


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
