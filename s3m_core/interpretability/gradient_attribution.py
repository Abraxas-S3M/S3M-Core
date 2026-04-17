"""Gradient-based attribution from model logits to SAE features."""

from __future__ import annotations

import logging
from typing import Any, Dict

import torch

from .sparse_autoencoder import SparseAutoencoder

logger = logging.getLogger(__name__)


class GradientAttribution:
    """Estimate causal contribution of SAE features to token logits."""

    def __init__(self) -> None:
        """Initialize attribution utility."""
        logger.debug("Initialized GradientAttribution utility")

    def attribute_to_features(
        self,
        model: Any,
        sae: SparseAutoencoder,
        input_ids: torch.Tensor,
        target_token_idx: int,
        target_layer: int,
    ) -> Dict[int, float]:
        """Compute SAE feature attributions for a specific output token logit."""
        normalized_ids = self._normalize_input_ids(input_ids)
        model_device = self._infer_model_device(model)
        normalized_ids = normalized_ids.to(model_device)
        layers = self._resolve_layers(model)
        if target_layer < 0 or target_layer >= len(layers):
            raise ValueError(
                f"target_layer must be in [0, {len(layers) - 1}], got {target_layer}"
            )

        captured: Dict[str, torch.Tensor] = {}

        def hook_fn(_: Any, __: Any, output: Any) -> None:
            layer_output = output[0] if isinstance(output, tuple) else output
            if not torch.is_tensor(layer_output):
                raise TypeError("Layer output is not a torch.Tensor")
            layer_output.retain_grad()
            captured["activations"] = layer_output

        handle = layers[target_layer].register_forward_hook(hook_fn)
        was_training = model.training
        model.eval()
        try:
            outputs = model(input_ids=normalized_ids)
            logits = self._extract_logits(outputs)
            if logits.ndim != 3:
                raise ValueError(f"Expected logits shape [batch, seq, vocab], got {tuple(logits.shape)}")
            position = self._normalize_token_index(target_token_idx, logits.shape[1])
            target_token_id = int(normalized_ids[0, position].item())
            target_logit = logits[0, position, target_token_id]

            model.zero_grad(set_to_none=True)
            sae.zero_grad(set_to_none=True)
            target_logit.backward()
        finally:
            handle.remove()
            if was_training:
                model.train()

        if "activations" not in captured:
            raise RuntimeError("Failed to capture target layer activations")
        layer_activations = captured["activations"]
        activation_grads = layer_activations.grad
        if activation_grads is None:
            raise RuntimeError("Activation gradients were not retained")

        position = self._normalize_token_index(target_token_idx, layer_activations.shape[1])
        activation_vector = layer_activations[0, position, :].detach().to(sae.device)
        gradient_vector = activation_grads[0, position, :].detach().to(sae.device)

        with torch.no_grad():
            feature_values = sae.encode(activation_vector)
            if feature_values.ndim != 1:
                feature_values = feature_values.squeeze(0)
            # Chain rule: d(logit)/d(feature_i) = grad_residual · decoder_column_i.
            decoder_weights = sae.decoder.weight.detach()
            directional_gradients = torch.matmul(gradient_vector, decoder_weights)
            attribution_tensor = directional_gradients * feature_values

        attributions = {
            int(index): float(attribution_tensor[index].detach().cpu().item())
            for index in range(attribution_tensor.shape[0])
            if abs(float(attribution_tensor[index].detach().cpu().item())) > 1e-12
        }
        logger.info(
            "Computed %s non-zero feature attributions for target_layer=%s token_idx=%s",
            len(attributions),
            target_layer,
            target_token_idx,
        )
        return attributions

    @staticmethod
    def _normalize_input_ids(input_ids: torch.Tensor) -> torch.Tensor:
        """Normalize input_ids to shape [batch, seq]."""
        if input_ids.ndim == 1:
            normalized = input_ids.unsqueeze(0)
        elif input_ids.ndim == 2:
            normalized = input_ids
        else:
            raise ValueError(f"input_ids must be 1D or 2D, got shape {tuple(input_ids.shape)}")
        if normalized.shape[0] < 1 or normalized.shape[1] < 1:
            raise ValueError("input_ids must include at least one token")
        return normalized.long()

    @staticmethod
    def _normalize_token_index(token_index: int, sequence_length: int) -> int:
        """Normalize token index with support for negative indices."""
        index = token_index
        if index < 0:
            index = sequence_length + index
        if index < 0 or index >= sequence_length:
            raise ValueError(
                f"target_token_idx must reference [0, {sequence_length - 1}], got {token_index}"
            )
        return index

    @staticmethod
    def _resolve_layers(model: Any) -> Any:
        """Resolve HuggingFace-like layer stack from model.model.layers."""
        if hasattr(model, "model") and hasattr(model.model, "layers"):
            return model.model.layers
        raise ValueError("Model must expose layers at model.layers")

    @staticmethod
    def _infer_model_device(model: Any) -> torch.device:
        """Infer active model device from first parameter."""
        parameter = next(model.parameters(), None)
        if parameter is None:
            return torch.device("cpu")
        return parameter.device

    @staticmethod
    def _extract_logits(outputs: Any) -> torch.Tensor:
        """Extract logits tensor from model forward outputs."""
        if hasattr(outputs, "logits"):
            return outputs.logits
        if isinstance(outputs, dict) and "logits" in outputs:
            return outputs["logits"]
        if isinstance(outputs, tuple) and outputs and torch.is_tensor(outputs[0]):
            return outputs[0]
        raise ValueError("Model outputs do not include logits")
