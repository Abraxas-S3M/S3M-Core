"""Federated adapter merge math for disconnected edge collaboration."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

try:
    import torch

    TORCH_AVAILABLE = True
except Exception:  # pragma: no cover - optional dependency
    torch = None  # type: ignore
    TORCH_AVAILABLE = False

logger = logging.getLogger("s3m.training.federated_aggregator")


class FederatedAggregator:
    """Aggregates LoRA adapter deltas across edge nodes without networking.

    Military/tactical context:
    Nodes may reconnect intermittently after contested-spectrum operations. This
    class merges whatever updates are available so headquarters can build an
    improved shared adapter even with partial unit participation.
    """

    SUPPORTED_STRATEGIES = {"fedavg", "median", "trimmed_mean"}

    def __init__(self, aggregation_strategy: str = "fedavg") -> None:
        if not TORCH_AVAILABLE or torch is None:
            raise RuntimeError("torch is required for federated adapter aggregation")
        if aggregation_strategy not in self.SUPPORTED_STRATEGIES:
            raise ValueError(f"aggregation_strategy must be one of {sorted(self.SUPPORTED_STRATEGIES)}")
        self.aggregation_strategy = aggregation_strategy
        self._updates: dict[str, dict[str, Any]] = {}
        self._merged: dict[str, torch.Tensor] = {}

    @staticmethod
    def _to_tensor(value: Any) -> torch.Tensor:
        if isinstance(value, torch.Tensor):
            return value.detach().cpu().float().clone()
        return torch.as_tensor(value, dtype=torch.float32).cpu()

    def register_update(self, node_id: str, adapter_weights: dict, n_samples: int) -> None:
        """Register a single node's adapter delta payload."""
        if not isinstance(node_id, str) or not node_id.strip():
            raise ValueError("node_id must be a non-empty string")
        if not isinstance(adapter_weights, dict) or not adapter_weights:
            raise ValueError("adapter_weights must be a non-empty dictionary")
        if int(n_samples) <= 0:
            raise ValueError("n_samples must be > 0")

        converted = {name: self._to_tensor(weight) for name, weight in adapter_weights.items()}
        self._updates[node_id] = {"weights": converted, "n_samples": int(n_samples)}

    def _aggregate_key_fedavg(self, tensors: list[torch.Tensor], counts: list[int]) -> torch.Tensor:
        total = float(sum(counts))
        if total <= 0.0:
            return torch.mean(torch.stack(tensors, dim=0), dim=0)
        weighted_sum = torch.zeros_like(tensors[0])
        for tensor, count in zip(tensors, counts):
            weighted_sum += tensor * (float(count) / total)
        return weighted_sum

    @staticmethod
    def _aggregate_key_median(tensors: list[torch.Tensor]) -> torch.Tensor:
        stacked = torch.stack(tensors, dim=0)
        return torch.median(stacked, dim=0).values

    @staticmethod
    def _aggregate_key_trimmed_mean(tensors: list[torch.Tensor]) -> torch.Tensor:
        stacked = torch.stack(tensors, dim=0)
        if stacked.shape[0] < 3:
            return torch.mean(stacked, dim=0)
        trim = max(1, int(stacked.shape[0] * 0.1))
        if trim * 2 >= stacked.shape[0]:
            return torch.mean(stacked, dim=0)
        sorted_vals, _ = torch.sort(stacked, dim=0)
        trimmed = sorted_vals[trim : stacked.shape[0] - trim]
        return torch.mean(trimmed, dim=0)

    def aggregate(self) -> dict:
        """Aggregate all currently registered updates and return merged weights."""
        if not self._updates:
            self._merged = {}
            return {}

        all_keys: set[str] = set()
        for payload in self._updates.values():
            all_keys.update(payload["weights"].keys())

        merged: dict[str, torch.Tensor] = {}
        for key in all_keys:
            tensors: list[torch.Tensor] = []
            counts: list[int] = []
            reference_shape = None

            for payload in self._updates.values():
                weight = payload["weights"].get(key)
                if weight is None:
                    continue
                tensor = self._to_tensor(weight)
                if reference_shape is None:
                    reference_shape = tuple(tensor.shape)
                if tuple(tensor.shape) != reference_shape:
                    logger.warning("Skipping incompatible tensor shape for key=%s", key)
                    continue
                tensors.append(tensor)
                counts.append(int(payload["n_samples"]))

            if not tensors:
                continue

            if self.aggregation_strategy == "fedavg":
                merged[key] = self._aggregate_key_fedavg(tensors, counts)
            elif self.aggregation_strategy == "median":
                merged[key] = self._aggregate_key_median(tensors)
            else:
                merged[key] = self._aggregate_key_trimmed_mean(tensors)

        self._merged = merged
        return {name: tensor.clone() for name, tensor in merged.items()}

    def export_merged(self, output_path: str) -> str:
        """Save merged adapter tensor dictionary to disk and return path."""
        if not isinstance(output_path, str) or not output_path.strip():
            raise ValueError("output_path must be a non-empty string")

        if not self._merged:
            self.aggregate()
        if not self._merged:
            raise RuntimeError("No merged adapter weights available for export")

        target = Path(output_path)
        if target.suffix:
            target.parent.mkdir(parents=True, exist_ok=True)
        else:
            target.mkdir(parents=True, exist_ok=True)
            target = target / "merged_adapter.pt"

        torch.save({k: v.cpu() for k, v in self._merged.items()}, str(target))
        return str(target)
