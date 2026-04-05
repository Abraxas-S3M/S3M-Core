"""
S3M Sparse Mixture-of-Experts — CPU optimized.

Military/tactical context:
Sparse activation allows larger representational capacity while preserving
deterministic CPU-time budgets needed on edge hardware during mission load.
"""

from __future__ import annotations

import json
import logging
import math
import threading
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from pydantic import BaseModel, Field

try:
    import numpy as np

    NP_AVAILABLE = True
except Exception:  # pragma: no cover - optional runtime guard
    np = None  # type: ignore[assignment]
    NP_AVAILABLE = False

logger = logging.getLogger(__name__)


class MoEConfig(BaseModel):
    """Configuration for sparse MoE."""

    n_experts: int = Field(default=16, ge=2, le=256)
    top_k: int = Field(default=2, ge=1, le=8)
    input_dim: int = Field(default=256, ge=8, le=8192)
    expert_hidden_dim: int = Field(default=128, ge=8, le=4096)
    output_dim: int = Field(default=256, ge=8, le=8192)
    load_balance_weight: float = Field(default=0.01, ge=0.0, le=10.0)
    noise_std: float = Field(default=0.1, ge=0.0, le=5.0)
    capacity_factor: float = Field(default=1.25, ge=1.0, le=4.0)


class ExpertRouter:
    """Top-k linear gating router for expert selection."""

    def __init__(self, input_dim: int, n_experts: int, top_k: int = 2, noise_std: float = 0.1) -> None:
        if not NP_AVAILABLE or np is None:
            raise RuntimeError("NumPy required for ExpertRouter")
        if top_k <= 0 or n_experts <= 1:
            raise ValueError("top_k must be > 0 and n_experts must be > 1")
        self._n_experts = int(n_experts)
        self._top_k = int(min(top_k, n_experts))
        self._noise_std = float(noise_std)
        scale = math.sqrt(2.0 / (input_dim + n_experts))
        self._gate_weights = np.random.randn(input_dim, n_experts).astype(np.float64) * scale
        self._gate_bias = np.zeros(n_experts, dtype=np.float64)
        self._usage_counts = np.zeros(n_experts, dtype=np.float64)

    def route(self, x: "np.ndarray", training: bool = False) -> Tuple[List[int], "np.ndarray"]:
        logits = x @ self._gate_weights + self._gate_bias
        if training and self._noise_std > 0:
            logits += np.random.randn(*logits.shape) * self._noise_std

        top_indices = np.argsort(logits.flatten())[-self._top_k :][::-1].tolist()
        selected_logits = np.asarray([float(logits.flatten()[idx]) for idx in top_indices], dtype=np.float64)
        max_logit = float(np.max(selected_logits))
        exp_logits = np.exp(selected_logits - max_logit)
        gate_weights = exp_logits / (float(np.sum(exp_logits)) + 1e-10)

        for idx in top_indices:
            self._usage_counts[idx] += 1.0

        return top_indices, gate_weights

    def load_balance_loss(self) -> float:
        total = float(np.sum(self._usage_counts)) or 1.0
        fractions = self._usage_counts / total
        ideal = 1.0 / float(self._n_experts)
        return float(np.sum((fractions - ideal) ** 2)) * float(self._n_experts)

    def reset_usage(self) -> None:
        self._usage_counts = np.zeros(self._n_experts, dtype=np.float64)

    def get_state(self) -> Dict[str, Any]:
        return {
            "gate_weights": self._gate_weights.tolist(),
            "gate_bias": self._gate_bias.tolist(),
            "usage_counts": self._usage_counts.tolist(),
            "n_experts": self._n_experts,
            "top_k": self._top_k,
            "noise_std": self._noise_std,
        }

    def load_state(self, state: Dict[str, Any]) -> None:
        self._gate_weights = np.asarray(state["gate_weights"], dtype=np.float64)
        self._gate_bias = np.asarray(state["gate_bias"], dtype=np.float64)
        self._usage_counts = np.asarray(state.get("usage_counts", [0.0] * self._n_experts), dtype=np.float64)
        self._n_experts = int(state.get("n_experts", self._n_experts))
        self._top_k = int(state.get("top_k", self._top_k))
        self._noise_std = float(state.get("noise_std", self._noise_std))


class _Expert:
    """Single expert: 2-layer MLP with ReLU."""

    def __init__(self, input_dim: int, hidden_dim: int, output_dim: int) -> None:
        if not NP_AVAILABLE or np is None:
            raise RuntimeError("NumPy required for experts")
        scale1 = math.sqrt(2.0 / (input_dim + hidden_dim))
        scale2 = math.sqrt(2.0 / (hidden_dim + output_dim))
        self.w1 = np.random.randn(input_dim, hidden_dim).astype(np.float64) * scale1
        self.b1 = np.zeros(hidden_dim, dtype=np.float64)
        self.w2 = np.random.randn(hidden_dim, output_dim).astype(np.float64) * scale2
        self.b2 = np.zeros(output_dim, dtype=np.float64)

    def forward(self, x: "np.ndarray") -> "np.ndarray":
        hidden = x @ self.w1 + self.b1
        hidden = np.maximum(hidden, 0.0)
        return hidden @ self.w2 + self.b2

    def get_state(self) -> Dict[str, Any]:
        return {
            "w1": self.w1.tolist(),
            "b1": self.b1.tolist(),
            "w2": self.w2.tolist(),
            "b2": self.b2.tolist(),
        }

    def load_state(self, state: Dict[str, Any]) -> None:
        self.w1 = np.asarray(state["w1"], dtype=np.float64)
        self.b1 = np.asarray(state["b1"], dtype=np.float64)
        self.w2 = np.asarray(state["w2"], dtype=np.float64)
        self.b2 = np.asarray(state["b2"], dtype=np.float64)


class SparseMoELayer:
    """Sparse MoE layer activating only top-k experts per input."""

    def __init__(self, config: Optional[MoEConfig] = None) -> None:
        self.config = config or MoEConfig()
        if self.config.top_k > self.config.n_experts:
            raise ValueError("top_k cannot exceed n_experts")
        if not NP_AVAILABLE or np is None:
            raise RuntimeError("NumPy required for SparseMoELayer")
        self._router = ExpertRouter(
            input_dim=self.config.input_dim,
            n_experts=self.config.n_experts,
            top_k=self.config.top_k,
            noise_std=self.config.noise_std,
        )
        self._experts = [
            _Expert(self.config.input_dim, self.config.expert_hidden_dim, self.config.output_dim)
            for _ in range(self.config.n_experts)
        ]
        self._lock = threading.RLock()

    def forward(self, x: "np.ndarray", training: bool = False) -> "np.ndarray":
        with self._lock:
            if x.ndim == 1:
                x = x.reshape(1, -1)
            if x.shape[1] != self.config.input_dim:
                raise ValueError(f"Expected input_dim={self.config.input_dim}, received {x.shape[1]}")

            outputs = np.zeros((x.shape[0], self.config.output_dim), dtype=np.float64)
            for row_index in range(x.shape[0]):
                expert_ids, gate_weights = self._router.route(x[row_index : row_index + 1], training=training)
                for gate_index, expert_id in enumerate(expert_ids):
                    outputs[row_index] += float(gate_weights[gate_index]) * self._experts[expert_id].forward(x[row_index])
            return outputs.squeeze()

    def active_parameter_fraction(self) -> float:
        return float(self.config.top_k) / float(self.config.n_experts)

    def load_balance_loss(self) -> float:
        return self._router.load_balance_loss()

    def reset_balance_tracking(self) -> None:
        self._router.reset_usage()

    def get_state(self) -> Dict[str, Any]:
        with self._lock:
            return {
                "config": self.config.model_dump(),
                "router": self._router.get_state(),
                "experts": [expert.get_state() for expert in self._experts],
            }

    def load_state(self, state: Dict[str, Any]) -> None:
        with self._lock:
            config_data = state.get("config")
            if isinstance(config_data, dict):
                self.config = MoEConfig.model_validate(config_data)
            router_state = state.get("router", {})
            expert_states = state.get("experts", [])
            if len(expert_states) != len(self._experts):
                self._experts = [
                    _Expert(self.config.input_dim, self.config.expert_hidden_dim, self.config.output_dim)
                    for _ in range(self.config.n_experts)
                ]
            self._router.load_state(router_state)
            for expert, expert_state in zip(self._experts, expert_states):
                expert.load_state(expert_state)

    def save_checkpoint(self, path: str) -> str:
        checkpoint_path = Path(path)
        if not checkpoint_path.suffix:
            checkpoint_path = checkpoint_path / "sparse_moe_checkpoint.json"
        checkpoint_path.parent.mkdir(parents=True, exist_ok=True)
        tmp_path = checkpoint_path.with_suffix(checkpoint_path.suffix + ".tmp")
        with tmp_path.open("w", encoding="utf-8") as handle:
            json.dump(self.get_state(), handle, sort_keys=True)
            handle.write("\n")
        tmp_path.replace(checkpoint_path)
        return str(checkpoint_path)

    def load_checkpoint(self, path: str) -> None:
        checkpoint_path = Path(path)
        if not checkpoint_path.exists():
            raise FileNotFoundError(f"MoE checkpoint not found: {checkpoint_path}")
        with checkpoint_path.open("r", encoding="utf-8") as handle:
            state = json.load(handle)
        self.load_state(state)


class MoEInferenceEngine:
    """High-level wrapper for feature-dict inference with sparse MoE."""

    def __init__(self, config: Optional[MoEConfig] = None) -> None:
        self.config = config or MoEConfig()
        self._layer = SparseMoELayer(self.config)
        self._inference_count = 0
        self._lock = threading.RLock()

    def infer(self, features: Dict[str, float]) -> "np.ndarray":
        if not NP_AVAILABLE or np is None:
            raise RuntimeError("NumPy required for MoE inference")
        if not isinstance(features, dict) or not features:
            raise ValueError("features must be a non-empty dictionary")

        vector = np.zeros(self.config.input_dim, dtype=np.float64)
        for key, value in features.items():
            if not isinstance(key, str) or not key:
                raise ValueError("feature keys must be non-empty strings")
            if not isinstance(value, (int, float)) or not math.isfinite(float(value)):
                raise ValueError(f"feature '{key}' must be finite")
            index = hash(key) % self.config.input_dim
            vector[index] += float(value)

        with self._lock:
            self._inference_count += 1
        return self._layer.forward(vector)

    def stats(self) -> Dict[str, Any]:
        with self._lock:
            return {
                "inference_count": self._inference_count,
                "active_fraction": self._layer.active_parameter_fraction(),
                "load_balance_loss": self._layer.load_balance_loss(),
                "n_experts": self.config.n_experts,
                "top_k": self.config.top_k,
            }

    def save_checkpoint(self, path: str) -> str:
        checkpoint_path = Path(path)
        if not checkpoint_path.suffix:
            checkpoint_path = checkpoint_path / "moe_engine_checkpoint.json"
        checkpoint_path.parent.mkdir(parents=True, exist_ok=True)
        tmp_path = checkpoint_path.with_suffix(checkpoint_path.suffix + ".tmp")
        with self._lock:
            payload = {
                "config": self.config.model_dump(),
                "inference_count": self._inference_count,
                "layer_state": self._layer.get_state(),
            }
        with tmp_path.open("w", encoding="utf-8") as handle:
            json.dump(payload, handle, sort_keys=True)
            handle.write("\n")
        tmp_path.replace(checkpoint_path)
        return str(checkpoint_path)

    def load_checkpoint(self, path: str) -> None:
        checkpoint_path = Path(path)
        if not checkpoint_path.exists():
            raise FileNotFoundError(f"MoE engine checkpoint not found: {checkpoint_path}")
        with checkpoint_path.open("r", encoding="utf-8") as handle:
            payload = json.load(handle)
        with self._lock:
            self.config = MoEConfig.model_validate(payload.get("config", {}))
            self._inference_count = int(payload.get("inference_count", 0))
            self._layer.load_state(payload.get("layer_state", {}))

