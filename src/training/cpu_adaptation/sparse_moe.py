"""Sparse mixture-of-experts layer with CPU-safe fallback execution."""

from __future__ import annotations

from typing import Sequence, Tuple

import numpy as np

try:
    import torch  # type: ignore

    _TORCH_AVAILABLE = True
except Exception:  # pragma: no cover - optional dependency
    torch = None  # type: ignore[assignment]
    _TORCH_AVAILABLE = False


class SparseMoELayer:
    """
    Deterministic sparse MoE layer for edge adaptation workloads.

    When torch is unavailable, this layer still routes and executes experts
    with NumPy so tactical training tasks degrade gracefully.
    """

    def __init__(
        self,
        input_dim: int,
        num_experts: int = 4,
        top_k: int = 2,
        seed: int = 7,
    ) -> None:
        if input_dim <= 0:
            raise ValueError("input_dim must be > 0")
        if num_experts <= 0:
            raise ValueError("num_experts must be > 0")
        if top_k <= 0 or top_k > num_experts:
            raise ValueError("top_k must be in [1, num_experts]")

        self.input_dim = int(input_dim)
        self.num_experts = int(num_experts)
        self.top_k = int(top_k)
        self.torch_available = _TORCH_AVAILABLE

        rng = np.random.default_rng(seed)
        # Tactical context: small deterministic init avoids startup spikes on edge nodes.
        self._gate_matrix = rng.normal(0.0, 0.05, size=(self.num_experts, self.input_dim))
        self._expert_scales = rng.normal(1.0, 0.05, size=(self.num_experts, self.input_dim))

    def route(self, inputs: Sequence[float]) -> Tuple[np.ndarray, np.ndarray]:
        vector = self._validate_vector(inputs)
        logits = self._gate_matrix @ vector
        winner_indices = np.argsort(logits)[-self.top_k :][::-1]
        top_logits = logits[winner_indices]
        exp_logits = np.exp(top_logits - np.max(top_logits))
        weights = exp_logits / np.sum(exp_logits)
        return winner_indices.astype(int), weights.astype(float)

    def forward(self, inputs: Sequence[float]) -> np.ndarray:
        vector = self._validate_vector(inputs)
        indices, weights = self.route(vector)
        mixed = np.zeros(self.input_dim, dtype=np.float64)
        for idx, weight in zip(indices.tolist(), weights.tolist()):
            mixed += float(weight) * (self._expert_scales[idx] * vector)
        return mixed

    def forward_torch(self, inputs: "torch.Tensor") -> "torch.Tensor":
        if not _TORCH_AVAILABLE:
            raise RuntimeError("torch is not available")
        if inputs.ndim != 1:
            raise ValueError("inputs must be a 1D tensor")
        vector = inputs.detach().cpu().numpy()
        out = self.forward(vector)
        return torch.as_tensor(out, dtype=inputs.dtype, device=inputs.device)

    def __call__(self, inputs: Sequence[float]) -> np.ndarray:
        return self.forward(inputs)

    def _validate_vector(self, inputs: Sequence[float]) -> np.ndarray:
        vector = np.asarray(inputs, dtype=np.float64).reshape(-1)
        if vector.shape[0] != self.input_dim:
            raise ValueError(
                f"input length mismatch: expected {self.input_dim}, got {vector.shape[0]}"
            )
        return vector
