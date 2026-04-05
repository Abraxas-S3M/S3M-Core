"""
S3M Online Stream Learner — CPU-native incremental learning.

Military/tactical context:
This module supports in-mission adaptation on constrained edge nodes where
large batch retraining is unavailable. Models update per sample and can be
checkpointed frequently for crash-safe recovery during contested operations.
"""

from __future__ import annotations

import hashlib
import json
import logging
import math
import threading
import uuid
from collections import defaultdict, deque
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Deque, Dict, List, Optional, Tuple

from pydantic import BaseModel, Field

try:
    import numpy as np

    NP_AVAILABLE = True
except Exception:  # pragma: no cover - optional runtime guard
    np = None  # type: ignore[assignment]
    NP_AVAILABLE = False

logger = logging.getLogger(__name__)


class StreamConfig(BaseModel):
    """Configuration for online stream learning."""

    learning_rate: float = Field(default=0.01, gt=0.0, le=1.0)
    l2_regularization: float = Field(default=0.001, ge=0.0)
    feature_dimension: int = Field(default=256, ge=2, le=4096)
    hash_features: bool = True
    window_size: int = Field(default=1000, ge=10, le=100000)
    decay_rate: float = Field(default=0.999, ge=0.9, le=1.0)
    n_trees: int = Field(default=10, ge=1, le=100)
    max_tree_depth: int = Field(default=8, ge=2, le=20)


class PredictionRecord(BaseModel):
    """Record of one prediction/update event."""

    record_id: str = Field(default_factory=lambda: str(uuid.uuid4())[:12])
    timestamp: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    features_hash: str = ""
    prediction: float = 0.0
    label: Optional[float] = None
    loss: Optional[float] = None
    model_version: int = 0


class OnlineSGDClassifier:
    """
    Online binary classifier trained via per-sample SGD.

    Uses feature hashing to keep fixed memory on small CPU systems.
    """

    def __init__(self, config: Optional[StreamConfig] = None) -> None:
        self.config = config or StreamConfig()
        if not NP_AVAILABLE or np is None:
            raise RuntimeError("NumPy required for OnlineSGDClassifier")
        self._dim = int(self.config.feature_dimension)
        self._weights = np.zeros(self._dim, dtype=np.float64)
        self._bias = 0.0
        self._lr = float(self.config.learning_rate)
        self._l2 = float(self.config.l2_regularization)
        self._decay = float(self.config.decay_rate)
        self._step = 0
        self._lock = threading.RLock()

    def _validate_features(self, features: Dict[str, float]) -> None:
        if not isinstance(features, dict) or not features:
            raise ValueError("features must be a non-empty dictionary")
        for key, value in features.items():
            if not isinstance(key, str) or not key:
                raise ValueError("feature keys must be non-empty strings")
            if not isinstance(value, (int, float)) or not math.isfinite(float(value)):
                raise ValueError(f"feature '{key}' must be a finite number")

    def _hash_features(self, features: Dict[str, float]) -> "np.ndarray":
        x = np.zeros(self._dim, dtype=np.float64)
        for key, value in features.items():
            digest = hashlib.md5(key.encode("utf-8")).hexdigest()
            index = int(digest, 16) % self._dim
            x[index] += float(value)
        return x

    @staticmethod
    def _sigmoid(logit: float) -> float:
        clipped = max(-500.0, min(500.0, logit))
        return 1.0 / (1.0 + math.exp(-clipped))

    def predict(self, features: Dict[str, float]) -> float:
        self._validate_features(features)
        x = self._hash_features(features)
        with self._lock:
            logit = float(np.dot(self._weights, x) + self._bias)
        return self._sigmoid(logit)

    def update(self, features: Dict[str, float], label: float) -> float:
        self._validate_features(features)
        if not isinstance(label, (int, float)) or not math.isfinite(float(label)):
            raise ValueError("label must be a finite number")
        y = float(label)
        x = self._hash_features(features)

        with self._lock:
            self._step += 1
            lr = self._lr / (1.0 + self._decay * self._step * 0.001)

            logit = float(np.dot(self._weights, x) + self._bias)
            pred = self._sigmoid(logit)
            error = pred - y
            loss = -y * math.log(pred + 1e-15) - (1.0 - y) * math.log(1.0 - pred + 1e-15)

            self._weights -= lr * (error * x + self._l2 * self._weights)
            self._bias -= lr * error
            return float(loss)

    def get_state(self) -> Dict[str, Any]:
        with self._lock:
            return {
                "weights": self._weights.tolist(),
                "bias": float(self._bias),
                "step": int(self._step),
                "learning_rate": float(self._lr),
            }

    def load_state(self, state: Dict[str, Any]) -> None:
        if not isinstance(state, dict):
            raise TypeError("state must be a dictionary")
        weights = state.get("weights")
        if not isinstance(weights, list) or len(weights) != self._dim:
            raise ValueError("state.weights must match feature dimension")
        with self._lock:
            self._weights = np.asarray(weights, dtype=np.float64)
            self._bias = float(state.get("bias", 0.0))
            self._step = int(state.get("step", 0))


class _OnlineTreeNode:
    """Incremental decision tree node with bounded split stats."""

    def __init__(self, depth: int = 0, max_depth: int = 8) -> None:
        self.depth = int(depth)
        self.max_depth = int(max_depth)
        self.count = 0
        self.label_sum = 0.0
        self.label_sq_sum = 0.0
        self.split_feature: Optional[str] = None
        self.split_value = 0.0
        self.left: Optional[_OnlineTreeNode] = None
        self.right: Optional[_OnlineTreeNode] = None
        self._feature_stats: Dict[str, List[float]] = defaultdict(list)
        self._split_threshold = 50

    def predict(self, features: Dict[str, float]) -> float:
        if self.split_feature and self.left and self.right:
            value = float(features.get(self.split_feature, 0.0))
            return self.left.predict(features) if value <= self.split_value else self.right.predict(features)
        return float(self.label_sum / max(self.count, 1))

    def update(self, features: Dict[str, float], label: float) -> None:
        self.count += 1
        self.label_sum += float(label)
        self.label_sq_sum += float(label) * float(label)

        if self.split_feature and self.left and self.right:
            value = float(features.get(self.split_feature, 0.0))
            if value <= self.split_value:
                self.left.update(features, label)
            else:
                self.right.update(features, label)
            return

        for key, value in features.items():
            slot = self._feature_stats[key]
            if len(slot) < 200:
                slot.append(float(value))

        if self.count >= self._split_threshold and self.depth < self.max_depth:
            self._try_split()

    def _try_split(self) -> None:
        if self.count < self._split_threshold:
            return

        parent_var = self.label_sq_sum / max(self.count, 1) - (self.label_sum / max(self.count, 1)) ** 2
        best_feature: Optional[str] = None
        best_value = 0.0
        best_gain = 0.0

        for feature_name, values in self._feature_stats.items():
            if len(values) < 10:
                continue
            sorted_values = sorted(values)
            median = sorted_values[len(sorted_values) // 2]
            left_count = sum(1 for value in sorted_values if value <= median)
            right_count = len(sorted_values) - left_count
            if left_count < 5 or right_count < 5:
                continue
            gain = parent_var * 0.1
            if gain > best_gain:
                best_gain = gain
                best_feature = feature_name
                best_value = float(median)

        if best_feature is not None:
            self.split_feature = best_feature
            self.split_value = best_value
            self.left = _OnlineTreeNode(depth=self.depth + 1, max_depth=self.max_depth)
            self.right = _OnlineTreeNode(depth=self.depth + 1, max_depth=self.max_depth)
            self._feature_stats.clear()

    def to_state(self) -> Dict[str, Any]:
        return {
            "depth": self.depth,
            "max_depth": self.max_depth,
            "count": self.count,
            "label_sum": self.label_sum,
            "label_sq_sum": self.label_sq_sum,
            "split_feature": self.split_feature,
            "split_value": self.split_value,
            "feature_stats": {key: list(values) for key, values in self._feature_stats.items()},
            "left": self.left.to_state() if self.left else None,
            "right": self.right.to_state() if self.right else None,
        }

    @classmethod
    def from_state(cls, state: Dict[str, Any]) -> "_OnlineTreeNode":
        node = cls(depth=int(state.get("depth", 0)), max_depth=int(state.get("max_depth", 8)))
        node.count = int(state.get("count", 0))
        node.label_sum = float(state.get("label_sum", 0.0))
        node.label_sq_sum = float(state.get("label_sq_sum", 0.0))
        node.split_feature = state.get("split_feature")
        node.split_value = float(state.get("split_value", 0.0))
        feature_stats = state.get("feature_stats", {})
        node._feature_stats = defaultdict(list, {key: list(values) for key, values in feature_stats.items()})
        if isinstance(state.get("left"), dict):
            node.left = cls.from_state(state["left"])
        if isinstance(state.get("right"), dict):
            node.right = cls.from_state(state["right"])
        return node


class OnlineTreeEnsemble:
    """Ensemble of incremental decision trees."""

    def __init__(self, n_trees: int = 10, max_depth: int = 8) -> None:
        if int(n_trees) <= 0:
            raise ValueError("n_trees must be > 0")
        if int(max_depth) < 2:
            raise ValueError("max_depth must be >= 2")
        self._trees = [_OnlineTreeNode(max_depth=int(max_depth)) for _ in range(int(n_trees))]
        self._lock = threading.RLock()

    def predict(self, features: Dict[str, float]) -> float:
        with self._lock:
            values = [tree.predict(features) for tree in self._trees]
        return float(sum(values) / max(len(values), 1))

    def update(self, features: Dict[str, float], label: float) -> None:
        with self._lock:
            for tree in self._trees:
                tree.update(features, label)

    def get_state(self) -> Dict[str, Any]:
        with self._lock:
            return {"trees": [tree.to_state() for tree in self._trees]}

    def load_state(self, state: Dict[str, Any]) -> None:
        trees_state = state.get("trees")
        if not isinstance(trees_state, list) or not trees_state:
            raise ValueError("state.trees must be a non-empty list")
        with self._lock:
            self._trees = [_OnlineTreeNode.from_state(item) for item in trees_state]


class StreamLearner:
    """
    Unified online learner with sliding-window metrics and checkpoint support.
    """

    def __init__(self, config: Optional[StreamConfig] = None) -> None:
        self.config = config or StreamConfig()
        self._sgd = OnlineSGDClassifier(self.config) if NP_AVAILABLE else None
        self._trees = OnlineTreeEnsemble(self.config.n_trees, self.config.max_tree_depth)
        self._history: Deque[PredictionRecord] = deque(maxlen=self.config.window_size)
        self._total_samples = 0
        self._total_loss = 0.0
        self._lock = threading.RLock()

    @staticmethod
    def _features_hash(features: Dict[str, float]) -> str:
        ordered = {key: float(features[key]) for key in sorted(features)}
        raw = json.dumps(ordered, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]

    def predict(self, features: Dict[str, float]) -> Dict[str, float]:
        outputs = {"tree_ensemble": self._trees.predict(features)}
        if self._sgd is not None:
            outputs["sgd"] = self._sgd.predict(features)
        outputs["consensus"] = float(sum(outputs.values()) / len(outputs))
        return outputs

    def learn(self, features: Dict[str, float], label: float) -> float:
        self._trees.update(features, label)
        tree_pred = self._trees.predict(features)
        losses = [(tree_pred - float(label)) ** 2]
        if self._sgd is not None:
            losses.append(self._sgd.update(features, label))
        avg_loss = float(sum(losses) / len(losses))

        with self._lock:
            self._total_samples += 1
            self._total_loss += avg_loss
            self._history.append(
                PredictionRecord(
                    features_hash=self._features_hash(features),
                    prediction=float(tree_pred),
                    label=float(label),
                    loss=avg_loss,
                    model_version=self._total_samples,
                )
            )
        return avg_loss

    def get_metrics(self) -> Dict[str, float]:
        with self._lock:
            losses = [record.loss for record in self._history if record.loss is not None]
            return {
                "total_samples": float(self._total_samples),
                "window_size": float(len(self._history)),
                "avg_loss": float(sum(losses) / len(losses)) if losses else 0.0,
                "cumulative_avg_loss": float(self._total_loss / max(self._total_samples, 1)),
            }

    def save_checkpoint(self, path: str) -> str:
        """
        Save learner state atomically to JSON.

        Tactical context: frequent local snapshots let edge operators resume
        adaptation quickly after process restarts in degraded environments.
        """

        target = Path(path)
        if not target.suffix:
            target = target / "stream_learner_checkpoint.json"
        target.parent.mkdir(parents=True, exist_ok=True)
        tmp_path = target.with_suffix(target.suffix + ".tmp")

        with self._lock:
            payload: Dict[str, Any] = {
                "config": self.config.model_dump(),
                "total_samples": self._total_samples,
                "total_loss": self._total_loss,
                "history": [record.model_dump() for record in self._history],
                "tree_state": self._trees.get_state(),
                "sgd_state": self._sgd.get_state() if self._sgd is not None else None,
            }
        with tmp_path.open("w", encoding="utf-8") as handle:
            json.dump(payload, handle, sort_keys=True)
            handle.write("\n")
        tmp_path.replace(target)
        return str(target)

    def load_checkpoint(self, path: str) -> None:
        checkpoint_path = Path(path)
        if not checkpoint_path.exists():
            raise FileNotFoundError(f"Checkpoint not found: {checkpoint_path}")
        with checkpoint_path.open("r", encoding="utf-8") as handle:
            payload = json.load(handle)

        with self._lock:
            self._total_samples = int(payload.get("total_samples", 0))
            self._total_loss = float(payload.get("total_loss", 0.0))
            self._history.clear()
            for item in payload.get("history", []):
                self._history.append(PredictionRecord.model_validate(item))
            self._trees.load_state(payload.get("tree_state", {}))
            if self._sgd is not None and isinstance(payload.get("sgd_state"), dict):
                self._sgd.load_state(payload["sgd_state"])

