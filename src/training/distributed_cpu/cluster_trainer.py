"""
S3M Distributed CPU Cluster Trainer.

Military/tactical context:
This trainer parallelizes gradient computation across local CPU workers when
accelerators are unavailable. It is tuned for 4-core / 16GB-class edge systems
and provides checkpoint/resume for interrupted field training operations.
"""

from __future__ import annotations

import hashlib
import json
import logging
import math
import os
import random
import threading
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

from pydantic import BaseModel, Field

try:
    import numpy as np

    NP_AVAILABLE = True
except Exception:  # pragma: no cover - optional runtime
    np = None  # type: ignore[assignment]
    NP_AVAILABLE = False

logger = logging.getLogger(__name__)

Sample = Tuple[Dict[str, float], float]


class ClusterTrainingConfig(BaseModel):
    """Configuration for distributed CPU training."""

    n_workers: int = Field(default=max(1, min(4, (os.cpu_count() or 4))), ge=1, le=32)
    feature_dimension: int = Field(default=256, ge=8, le=4096)
    learning_rate: float = Field(default=0.03, gt=0.0, le=1.0)
    l2_regularization: float = Field(default=0.0005, ge=0.0, le=1.0)
    batch_size: int = Field(default=64, ge=4, le=8192)
    max_epochs: int = Field(default=1, ge=1, le=1000)
    shuffle_each_epoch: bool = True
    checkpoint_every_steps: int = Field(default=25, ge=1, le=100000)
    checkpoint_dir: str = Field(default="checkpoints/distributed_cpu", min_length=1)
    seed: Optional[int] = None


class ClusterCheckpoint(BaseModel):
    """Serializable checkpoint descriptor for cluster training state."""

    checkpoint_id: str = Field(default_factory=lambda: str(uuid.uuid4())[:12])
    timestamp: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    step: int = 0
    epoch: int = 0
    avg_loss: float = 0.0
    path: str = ""


class ClusterTrainer:
    """
    Data-parallel logistic learner for CPU worker pools.

    Each worker computes gradients on a shard, then the trainer applies
    aggregated updates under a single lock to preserve consistency.
    """

    def __init__(self, config: Optional[ClusterTrainingConfig] = None) -> None:
        if not NP_AVAILABLE or np is None:
            raise RuntimeError("NumPy required for ClusterTrainer")
        self.config = config or ClusterTrainingConfig()
        self._weights = np.zeros(self.config.feature_dimension, dtype=np.float64)
        self._bias = 0.0
        self._step = 0
        self._epoch = 0
        self._loss_total = 0.0
        self._loss_count = 0
        self._lock = threading.RLock()
        self._rng = random.Random(self.config.seed)

    @staticmethod
    def _sigmoid(values: "np.ndarray") -> "np.ndarray":
        clipped = np.clip(values, -500.0, 500.0)
        return 1.0 / (1.0 + np.exp(-clipped))

    def _hash_features(self, features: Dict[str, float]) -> "np.ndarray":
        x = np.zeros(self.config.feature_dimension, dtype=np.float64)
        for key, value in features.items():
            if not isinstance(key, str) or not key:
                raise ValueError("feature keys must be non-empty strings")
            if not isinstance(value, (int, float)) or not math.isfinite(float(value)):
                raise ValueError(f"feature '{key}' must be a finite number")
            digest = hashlib.md5(key.encode("utf-8")).hexdigest()
            index = int(digest, 16) % self.config.feature_dimension
            x[index] += float(value)
        return x

    def _vectorize(self, batch: Sequence[Sample]) -> Tuple["np.ndarray", "np.ndarray"]:
        if not batch:
            raise ValueError("batch must contain at least one sample")
        x_mat = np.zeros((len(batch), self.config.feature_dimension), dtype=np.float64)
        y_vec = np.zeros(len(batch), dtype=np.float64)
        for row, (features, label) in enumerate(batch):
            if not isinstance(features, dict) or not features:
                raise ValueError("sample features must be a non-empty dictionary")
            if not isinstance(label, (int, float)) or not math.isfinite(float(label)):
                raise ValueError("sample label must be a finite number")
            x_mat[row] = self._hash_features(features)
            y_vec[row] = float(label)
        return x_mat, y_vec

    def _compute_shard_grad(
        self,
        shard: Sequence[Sample],
        weights_snapshot: "np.ndarray",
        bias_snapshot: float,
    ) -> Tuple["np.ndarray", float, float, int]:
        x_mat, y_vec = self._vectorize(shard)
        logits = x_mat @ weights_snapshot + bias_snapshot
        preds = self._sigmoid(logits)
        errors = preds - y_vec
        grad_w = (x_mat.T @ errors) / len(shard) + self.config.l2_regularization * weights_snapshot
        grad_b = float(np.mean(errors))
        losses = -y_vec * np.log(preds + 1e-15) - (1.0 - y_vec) * np.log(1.0 - preds + 1e-15)
        return grad_w, grad_b, float(np.mean(losses)), len(shard)

    def predict(self, features: Dict[str, float]) -> float:
        x = self._hash_features(features)
        with self._lock:
            logit = float(self._weights @ x + self._bias)
        return float(self._sigmoid(np.asarray([logit]))[0])

    def _split_batch(self, batch: Sequence[Sample]) -> List[List[Sample]]:
        workers = max(1, min(self.config.n_workers, len(batch)))
        shards: List[List[Sample]] = [[] for _ in range(workers)]
        for idx, sample in enumerate(batch):
            shards[idx % workers].append(sample)
        return [shard for shard in shards if shard]

    def train_batch(self, batch: Sequence[Sample]) -> float:
        if not batch:
            raise ValueError("batch must not be empty")
        with self._lock:
            w_snapshot = self._weights.copy()
            b_snapshot = float(self._bias)
        shards = self._split_batch(batch)

        with ThreadPoolExecutor(max_workers=len(shards)) as executor:
            futures = [
                executor.submit(self._compute_shard_grad, shard, w_snapshot, b_snapshot)
                for shard in shards
            ]
            shard_results = [future.result() for future in futures]

        total_count = sum(item[3] for item in shard_results)
        if total_count <= 0:
            return 0.0

        grad_w = np.zeros_like(w_snapshot)
        grad_b = 0.0
        avg_loss = 0.0
        for shard_grad_w, shard_grad_b, shard_loss, shard_count in shard_results:
            scale = shard_count / total_count
            grad_w += shard_grad_w * scale
            grad_b += shard_grad_b * scale
            avg_loss += shard_loss * scale

        with self._lock:
            self._weights -= self.config.learning_rate * grad_w
            self._bias -= self.config.learning_rate * grad_b
            self._step += 1
            self._loss_total += float(avg_loss)
            self._loss_count += 1

        if self._step % self.config.checkpoint_every_steps == 0:
            self.save_checkpoint()
        return float(avg_loss)

    def train(self, dataset: Sequence[Sample], epochs: Optional[int] = None) -> Dict[str, float]:
        if not dataset:
            raise ValueError("dataset must not be empty")
        num_epochs = int(epochs) if epochs is not None else int(self.config.max_epochs)
        if num_epochs <= 0:
            raise ValueError("epochs must be > 0")

        samples = list(dataset)
        last_loss = 0.0
        for _ in range(num_epochs):
            if self.config.shuffle_each_epoch:
                self._rng.shuffle(samples)
            for start in range(0, len(samples), self.config.batch_size):
                batch = samples[start : start + self.config.batch_size]
                last_loss = self.train_batch(batch)
            with self._lock:
                self._epoch += 1

        with self._lock:
            avg_loss = self._loss_total / max(self._loss_count, 1)
            return {
                "step": float(self._step),
                "epoch": float(self._epoch),
                "last_loss": float(last_loss),
                "avg_loss": float(avg_loss),
            }

    def get_state(self) -> Dict[str, Any]:
        with self._lock:
            return {
                "config": self.config.model_dump(),
                "weights": self._weights.tolist(),
                "bias": self._bias,
                "step": self._step,
                "epoch": self._epoch,
                "loss_total": self._loss_total,
                "loss_count": self._loss_count,
            }

    def load_state(self, state: Dict[str, Any]) -> None:
        if not isinstance(state, dict):
            raise TypeError("state must be a dictionary")
        with self._lock:
            cfg = state.get("config")
            if isinstance(cfg, dict):
                self.config = ClusterTrainingConfig.model_validate(cfg)
            self._weights = np.asarray(state["weights"], dtype=np.float64)
            if self._weights.shape != (self.config.feature_dimension,):
                raise ValueError("weights dimension mismatch with config.feature_dimension")
            self._bias = float(state.get("bias", 0.0))
            self._step = int(state.get("step", 0))
            self._epoch = int(state.get("epoch", 0))
            self._loss_total = float(state.get("loss_total", 0.0))
            self._loss_count = int(state.get("loss_count", 0))

    def save_checkpoint(self, path: Optional[str] = None, avg_loss: Optional[float] = None) -> ClusterCheckpoint:
        checkpoint_dir = Path(path) if path else Path(self.config.checkpoint_dir)
        if checkpoint_dir.suffix:
            checkpoint_file = checkpoint_dir
            checkpoint_file.parent.mkdir(parents=True, exist_ok=True)
        else:
            checkpoint_dir.mkdir(parents=True, exist_ok=True)
            checkpoint_file = checkpoint_dir / f"checkpoint-{self._step:09d}.json"
        tmp_file = checkpoint_file.with_suffix(checkpoint_file.suffix + ".tmp")

        with self._lock:
            current_avg_loss = avg_loss if avg_loss is not None else (self._loss_total / max(self._loss_count, 1))
            metadata = ClusterCheckpoint(
                step=self._step,
                epoch=self._epoch,
                avg_loss=float(current_avg_loss),
                path=str(checkpoint_file),
            )
            payload = {"metadata": metadata.model_dump(), "state": self.get_state()}

        with tmp_file.open("w", encoding="utf-8") as handle:
            json.dump(payload, handle, sort_keys=True)
            handle.write("\n")
        tmp_file.replace(checkpoint_file)
        return metadata

    def load_checkpoint(self, path: str) -> ClusterCheckpoint:
        checkpoint_path = Path(path)
        if not checkpoint_path.exists():
            raise FileNotFoundError(f"Checkpoint not found: {checkpoint_path}")
        with checkpoint_path.open("r", encoding="utf-8") as handle:
            payload = json.load(handle)
        self.load_state(payload["state"])
        return ClusterCheckpoint.model_validate(payload["metadata"])

    def resume_latest(self) -> Optional[ClusterCheckpoint]:
        checkpoint_dir = Path(self.config.checkpoint_dir)
        if checkpoint_dir.suffix:
            if checkpoint_dir.exists():
                return self.load_checkpoint(str(checkpoint_dir))
            return None
        if not checkpoint_dir.exists():
            return None
        candidates = sorted(checkpoint_dir.glob("checkpoint-*.json"))
        if not candidates:
            return None
        return self.load_checkpoint(str(candidates[-1]))

    def stats(self) -> Dict[str, float]:
        with self._lock:
            return {
                "step": float(self._step),
                "epoch": float(self._epoch),
                "avg_loss": float(self._loss_total / max(self._loss_count, 1)),
                "workers": float(self.config.n_workers),
            }

