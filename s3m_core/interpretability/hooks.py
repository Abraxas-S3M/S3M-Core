"""Activation hook manager for SAE-based threat monitoring."""

from __future__ import annotations

import logging
from typing import Any, List, Optional

import torch

from .feature_registry import ThreatAlert, ThreatFeatureRegistry
from .sparse_autoencoder import SparseAutoencoder

logger = logging.getLogger(__name__)


class ActivationHookManager:
    """Manage forward hooks to capture activations and evaluate threats."""

    def __init__(self) -> None:
        """Initialize hook manager state."""
        self._handles: List[Any] = []
        self._latest_activations: Optional[torch.Tensor] = None
        self._latest_alerts: List[ThreatAlert] = []
        logger.debug("Initialized ActivationHookManager")

    def register_hook(self, model: Any, layer_index: int) -> None:
        """Register a capture hook for one transformer layer."""
        layers = self._resolve_layers(model)
        if layer_index < 0 or layer_index >= len(layers):
            raise ValueError(
                f"layer_index must be in [0, {len(layers) - 1}], got {layer_index}"
            )

        def hook_fn(_: Any, __: Any, output: Any) -> None:
            output_tensor = output[0] if isinstance(output, tuple) else output
            if not torch.is_tensor(output_tensor):
                logger.warning("Hook output is not tensor; skipping capture")
                return
            self._latest_activations = output_tensor.detach()
            logger.debug(
                "Captured activations from layer=%s shape=%s",
                layer_index,
                tuple(self._latest_activations.shape),
            )

        handle = layers[layer_index].register_forward_hook(hook_fn)
        self._handles.append(handle)
        logger.info("Registered activation capture hook at layer_index=%s", layer_index)

    def get_activations(self) -> torch.Tensor:
        """Return the most recent captured activation tensor."""
        if self._latest_activations is None:
            raise RuntimeError("No activations captured yet. Run model forward first.")
        return self._latest_activations

    def register_sae_monitor(
        self,
        model: Any,
        sae: SparseAutoencoder,
        registry: ThreatFeatureRegistry,
        layer_index: int,
    ) -> None:
        """Register a monitor hook that converts activations into threat alerts."""
        layers = self._resolve_layers(model)
        if layer_index < 0 or layer_index >= len(layers):
            raise ValueError(
                f"layer_index must be in [0, {len(layers) - 1}], got {layer_index}"
            )

        def monitor_hook(_: Any, __: Any, output: Any) -> None:
            output_tensor = output[0] if isinstance(output, tuple) else output
            if not torch.is_tensor(output_tensor):
                logger.warning("Monitor hook output is not tensor; skipping monitor evaluation")
                return
            self._latest_activations = output_tensor.detach()
            with torch.no_grad():
                active_features = sae.get_active_features(self._latest_activations)
            self._latest_alerts = registry.evaluate(active_features)
            logger.info(
                "SAE monitor produced %s alerts at layer=%s",
                len(self._latest_alerts),
                layer_index,
            )

        handle = layers[layer_index].register_forward_hook(monitor_hook)
        self._handles.append(handle)
        logger.info("Registered SAE monitor hook at layer_index=%s", layer_index)

    def get_latest_alerts(self) -> List[ThreatAlert]:
        """Return alerts generated during the most recent forward pass."""
        return list(self._latest_alerts)

    def clear_hooks(self) -> None:
        """Remove all active hooks managed by this instance."""
        for handle in self._handles:
            handle.remove()
        removed = len(self._handles)
        self._handles.clear()
        logger.info("Cleared %s registered hooks", removed)

    @staticmethod
    def _resolve_layers(model: Any) -> Any:
        """Resolve HuggingFace-compatible layer list via model.layers."""
        if hasattr(model, "model") and hasattr(model.model, "layers"):
            return model.model.layers
        raise ValueError("Model must expose layers through model.layers")
