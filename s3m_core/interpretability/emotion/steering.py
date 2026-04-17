"""Residual-stream emotion steering for tactical safety behavior."""

from __future__ import annotations

from datetime import datetime, timezone
import logging
from typing import Any, Dict, List, Sequence

import torch
import torch.nn as nn


class EmotionSteering:
    """
    Apply additive concept vectors during forward passes.

    Tactical context:
    Steering is constrained to conservative fractions of residual norms so
    mission outputs remain coherent while discouraging rash behavior.
    """

    DEFAULT_MAX_STRENGTH: float = 0.3
    ABSOLUTE_MAX_STRENGTH: float = 0.5

    def __init__(
        self,
        emotion_vectors: Dict[str, Dict[int, torch.Tensor]],
        model: Any,
        target_layers: List[int],
    ):
        if not target_layers:
            raise ValueError("target_layers must include at least one layer")
        self.emotion_vectors = emotion_vectors
        self.model = model
        self.target_layers = sorted({int(layer) for layer in target_layers})
        self._active_hook_handles: List[Any] = []
        self.audit_trail: List[Dict[str, Any]] = []
        self.logger = logging.getLogger(__name__)

    def apply_steering(self, emotion_name: str, strength: float, direction: str = "positive") -> None:
        self._validate_strength(strength)
        if direction not in {"positive", "negative"}:
            raise ValueError("direction must be either 'positive' or 'negative'")
        if emotion_name not in self.emotion_vectors:
            raise KeyError(f"No steering vectors registered for concept '{emotion_name}'")

        sign = 1.0 if direction == "positive" else -1.0
        concept_vectors = self.emotion_vectors[emotion_name]
        for layer in self.target_layers:
            if layer not in concept_vectors:
                continue
            layer_module = self._resolve_layer_module(layer)
            steering_direction = concept_vectors[layer].detach().clone()

            def _hook(_module: nn.Module, _inputs: Any, output: Any) -> Any:
                residual = self._extract_tensor(output)
                if residual.numel() == 0:
                    return output
                residual_norm = residual.norm(dim=-1, keepdim=True).mean().detach()
                direction_tensor = steering_direction.to(device=residual.device, dtype=residual.dtype)
                direction_norm = torch.norm(direction_tensor).clamp_min(1e-8)
                scaling = float(sign * strength) * residual_norm / direction_norm
                delta = scaling * direction_tensor
                while delta.dim() < residual.dim():
                    delta = delta.unsqueeze(0)
                adjusted = residual + delta
                if torch.is_tensor(output):
                    return adjusted
                if isinstance(output, tuple):
                    return (adjusted, *output[1:])
                if isinstance(output, list):
                    return [adjusted, *output[1:]]
                return adjusted

            handle = layer_module.register_forward_hook(_hook)
            self._active_hook_handles.append(handle)

        self._record_audit(
            action="apply_steering",
            details={
                "emotion_name": emotion_name,
                "strength": float(strength),
                "direction": direction,
                "target_layers": list(self.target_layers),
            },
        )

    def apply_deliberation_boost(self, strength: float = 0.3) -> None:
        self._validate_strength(strength)
        self.apply_steering("valence", strength=strength, direction="negative")
        self.apply_steering("cautious", strength=strength, direction="positive")
        self.apply_steering("analytical", strength=strength, direction="positive")
        self._record_audit(
            action="apply_deliberation_boost",
            details={"strength": float(strength)},
        )

    def apply_recklessness_suppression(self, strength: float = 0.2) -> None:
        self._validate_strength(strength)
        self.apply_steering("frustration", strength=strength, direction="positive")
        self.apply_steering("paranoia", strength=strength, direction="positive")
        self._record_audit(
            action="apply_recklessness_suppression",
            details={"strength": float(strength)},
        )

    def remove_all_steering(self) -> None:
        for handle in self._active_hook_handles:
            try:
                handle.remove()
            except Exception:
                continue
        removed = len(self._active_hook_handles)
        self._active_hook_handles.clear()
        self._record_audit(
            action="remove_all_steering",
            details={"removed_hooks": removed},
        )

    def _validate_strength(self, strength: float) -> None:
        if strength < 0:
            raise ValueError("strength must be non-negative")
        if strength > self.ABSOLUTE_MAX_STRENGTH:
            raise ValueError(
                f"strength={strength:.3f} exceeds absolute safety limit "
                f"{self.ABSOLUTE_MAX_STRENGTH:.3f}"
            )
        if strength > self.DEFAULT_MAX_STRENGTH:
            raise ValueError(
                f"strength={strength:.3f} exceeds default safety maximum "
                f"{self.DEFAULT_MAX_STRENGTH:.3f}; higher values risk incoherent output"
            )

    def _record_audit(self, action: str, details: Dict[str, Any]) -> None:
        event = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "action": action,
            "details": dict(details),
        }
        self.audit_trail.append(event)
        self.logger.info("emotion_steering_audit %s", event)

    def _resolve_layer_module(self, layer_index: int) -> nn.Module:
        layer_paths: Sequence[Sequence[str]] = (
            ("model", "layers"),
            ("transformer", "h"),
            ("transformer", "layers"),
            ("layers",),
            ("blocks",),
        )
        for path in layer_paths:
            node = self.model
            valid_path = True
            for attribute in path:
                if not hasattr(node, attribute):
                    valid_path = False
                    break
                node = getattr(node, attribute)
            if not valid_path:
                continue
            if isinstance(node, (list, tuple, nn.ModuleList)):
                normalized_index = layer_index if layer_index >= 0 else len(node) + layer_index
                if 0 <= normalized_index < len(node):
                    module = node[normalized_index]
                    if isinstance(module, nn.Module):
                        return module
        named_modules = [module for _, module in self.model.named_modules()]
        normalized_index = layer_index if layer_index >= 0 else len(named_modules) + layer_index
        if 0 <= normalized_index < len(named_modules):
            return named_modules[normalized_index]
        raise IndexError(f"Unable to resolve target layer index {layer_index}")

    @staticmethod
    def _extract_tensor(output: Any) -> torch.Tensor:
        if torch.is_tensor(output):
            return output
        if isinstance(output, (list, tuple)) and output:
            first = output[0]
            if torch.is_tensor(first):
                return first
        raise TypeError("Layer output must be tensor-like for residual steering")

