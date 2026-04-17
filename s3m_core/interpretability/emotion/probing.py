"""Runtime emotion probing from residual activations."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Mapping, Protocol, Sequence

import torch


class ActivationHookManager(Protocol):
    """Protocol for activation retrieval adapters used by probing."""

    def get_layer_activation(self, layer: int) -> torch.Tensor:
        """Return the latest residual activation for a target layer."""


@dataclass(frozen=True)
class EmotionProfile:
    """Compact summary of current latent emotional posture."""

    valence: float
    arousal: float
    dominant_emotion: str
    secondary_emotion: str
    risk_flag: bool


class EmotionProbe:
    """
    Measure latent emotion state during inference.

    Tactical context:
    Risk is elevated when confidence-like valence and activation-like arousal
    are both high, because rushed high-energy states can reduce deliberation.
    """

    POSITIVE_LABELS: Sequence[str] = ("joy", "tranquility", "excitement", "surprise", "cautious", "analytical")
    NEGATIVE_LABELS: Sequence[str] = (
        "sadness",
        "anger",
        "fear",
        "disgust",
        "frustration",
        "desperation",
        "guilt",
        "paranoia",
        "reckless",
        "impulsive",
        "aggressive",
    )
    HIGH_AROUSAL_LABELS: Sequence[str] = (
        "anger",
        "fear",
        "frustration",
        "desperation",
        "excitement",
        "surprise",
        "paranoia",
        "reckless",
        "impulsive",
        "aggressive",
    )
    LOW_AROUSAL_LABELS: Sequence[str] = ("tranquility", "cautious", "analytical", "methodical", "sadness")
    HIGH_VALENCE_THRESHOLD: float = 0.35
    HIGH_AROUSAL_THRESHOLD: float = 0.35

    def __init__(
        self,
        emotion_vectors: Dict[str, Dict[int, torch.Tensor]],
        hook_manager: ActivationHookManager,
    ):
        self.emotion_vectors = emotion_vectors
        self.hook_manager = hook_manager

    def probe_current_state(self, layer: int) -> Dict[str, float]:
        activation = self._to_vector(self._get_layer_activation(layer))
        scores: Dict[str, float] = {}
        for emotion_name, vectors_by_layer in self.emotion_vectors.items():
            direction = vectors_by_layer.get(layer)
            if direction is None:
                continue
            direction_vector = self._to_vector(direction)
            if activation.numel() != direction_vector.numel():
                raise ValueError(
                    f"Activation dimension {activation.numel()} does not match vector "
                    f"dimension {direction_vector.numel()} for {emotion_name}"
                )
            normalized_direction = self._normalize(direction_vector)
            score = torch.dot(activation, normalized_direction).item()
            scores[emotion_name] = float(score)
        return scores

    def get_valence(self, layer: int) -> float:
        if "valence" in self.emotion_vectors and layer in self.emotion_vectors["valence"]:
            activation = self._to_vector(self._get_layer_activation(layer))
            direction = self._to_vector(self.emotion_vectors["valence"][layer])
            return float(torch.dot(activation, self._normalize(direction)).item())

        scores = self.probe_current_state(layer)
        positives = [scores[name] for name in self.POSITIVE_LABELS if name in scores]
        negatives = [scores[name] for name in self.NEGATIVE_LABELS if name in scores]
        if not positives and not negatives:
            return 0.0
        positive_score = sum(positives) / len(positives) if positives else 0.0
        negative_score = sum(negatives) / len(negatives) if negatives else 0.0
        return float(positive_score - negative_score)

    def get_arousal(self, layer: int) -> float:
        scores = self.probe_current_state(layer)
        high = [scores[name] for name in self.HIGH_AROUSAL_LABELS if name in scores]
        low = [scores[name] for name in self.LOW_AROUSAL_LABELS if name in scores]
        if not high and not low:
            return 0.0
        high_score = sum(high) / len(high) if high else 0.0
        low_score = sum(low) / len(low) if low else 0.0
        return float(high_score - low_score)

    def get_emotion_profile(self) -> EmotionProfile:
        layer = self._default_layer()
        scores = self.probe_current_state(layer)
        ranked = sorted(scores.items(), key=lambda item: item[1], reverse=True)
        dominant = ranked[0][0] if ranked else "unknown"
        secondary = ranked[1][0] if len(ranked) > 1 else "unknown"
        valence = self.get_valence(layer)
        arousal = self.get_arousal(layer)
        risk_flag = bool(
            valence >= self.HIGH_VALENCE_THRESHOLD and arousal >= self.HIGH_AROUSAL_THRESHOLD
        )
        return EmotionProfile(
            valence=valence,
            arousal=arousal,
            dominant_emotion=dominant,
            secondary_emotion=secondary,
            risk_flag=risk_flag,
        )

    def _default_layer(self) -> int:
        layers = sorted(
            {
                layer
                for vectors_by_layer in self.emotion_vectors.values()
                for layer in vectors_by_layer.keys()
            }
        )
        if not layers:
            raise ValueError("emotion_vectors is empty; at least one vector is required")
        return layers[0]

    def _get_layer_activation(self, layer: int) -> torch.Tensor:
        if hasattr(self.hook_manager, "get_layer_activation"):
            value = self.hook_manager.get_layer_activation(layer)
            if torch.is_tensor(value):
                return value
        if hasattr(self.hook_manager, "get_last_activation"):
            value = self.hook_manager.get_last_activation(layer)
            if torch.is_tensor(value):
                return value
        if hasattr(self.hook_manager, "get_current_activation"):
            value = self.hook_manager.get_current_activation(layer)
            if torch.is_tensor(value):
                return value
        activations = getattr(self.hook_manager, "activations", None)
        if isinstance(activations, Mapping):
            value = activations.get(layer)
            if torch.is_tensor(value):
                return value
        raise AttributeError("hook_manager does not expose a supported activation accessor")

    @staticmethod
    def _to_vector(tensor: torch.Tensor) -> torch.Tensor:
        if tensor.dim() == 1:
            return tensor
        if tensor.dim() == 2:
            return tensor.mean(dim=0)
        if tensor.dim() >= 3:
            return tensor.mean(dim=(0, 1))
        raise ValueError("Unsupported tensor dimensionality for emotion probing")

    @staticmethod
    def _normalize(vector: torch.Tensor) -> torch.Tensor:
        return vector / torch.norm(vector).clamp_min(1e-8)

