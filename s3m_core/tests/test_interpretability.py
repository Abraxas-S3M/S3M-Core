"""Unit tests for the S3M SAE interpretability engine."""

from __future__ import annotations

from types import SimpleNamespace

import torch
from torch import nn

from s3m_core.interpretability.feature_registry import ThreatFeatureRegistry
from s3m_core.interpretability.gradient_attribution import GradientAttribution
from s3m_core.interpretability.hooks import ActivationHookManager
from s3m_core.interpretability.sparse_autoencoder import SparseAutoencoder


class ToyTransformerLayer(nn.Module):
    """Minimal transformer-like layer for hook and attribution tests."""

    def __init__(self, hidden_dim: int) -> None:
        super().__init__()
        self.proj = nn.Linear(hidden_dim, hidden_dim)
        self.norm = nn.LayerNorm(hidden_dim)

    def forward(self, hidden_states: torch.Tensor) -> torch.Tensor:
        residual = hidden_states
        hidden_states = torch.tanh(self.proj(hidden_states))
        return self.norm(hidden_states + residual)


class ToyBackbone(nn.Module):
    """Backbone exposing HuggingFace-style model.layers."""

    def __init__(self, vocab_size: int, hidden_dim: int, n_layers: int) -> None:
        super().__init__()
        self.embed_tokens = nn.Embedding(vocab_size, hidden_dim)
        self.layers = nn.ModuleList(
            [ToyTransformerLayer(hidden_dim=hidden_dim) for _ in range(n_layers)]
        )


class ToyCausalLM(nn.Module):
    """Tiny causal LM compatible with interpretability hooks."""

    def __init__(self, vocab_size: int = 64, hidden_dim: int = 24, n_layers: int = 3) -> None:
        super().__init__()
        self.model = ToyBackbone(vocab_size=vocab_size, hidden_dim=hidden_dim, n_layers=n_layers)
        self.lm_head = nn.Linear(hidden_dim, vocab_size, bias=False)

    def forward(self, input_ids: torch.Tensor) -> SimpleNamespace:
        hidden_states = self.model.embed_tokens(input_ids)
        for layer in self.model.layers:
            hidden_states = layer(hidden_states)
        logits = self.lm_head(hidden_states)
        return SimpleNamespace(logits=logits)


def test_sae_encode_decode_roundtrip_loss_below_threshold() -> None:
    """SAE should reconstruct a simple dataset with low roundtrip MSE."""
    torch.manual_seed(11)
    input_dim = 12
    sae = SparseAutoencoder(input_dim=input_dim, hidden_dim=48, sparsity_coefficient=1e-4)
    dataset = torch.rand(2048, input_dim)
    sae.train_on_dataset(dataset=dataset, epochs=35, batch_size=128, lr=2e-3)
    sae.eval()
    with torch.no_grad():
        sample = dataset[:256].to(sae.device)
        reconstructions = sae.decode(sae.encode(sample))
        mse = nn.functional.mse_loss(reconstructions, sample).item()
    assert mse < 0.1


def test_feature_registry_flags_known_threat_patterns() -> None:
    """Registry should emit alerts when mapped feature indices are active."""
    registry = ThreatFeatureRegistry()
    active_features = {
        1: 0.91,
        4: 0.50,
        11: 0.82,
    }
    alerts = registry.evaluate(active_features)
    flagged_names = {alert.feature_name for alert in alerts}
    assert "security_bypass" in flagged_names
    assert "backdoor_vulnerability" in flagged_names
    assert "guilt_shame_moral_wrongdoing" in flagged_names

    high_alerts = registry.get_alerts_above_severity(alerts, min_severity="critical")
    assert {alert.feature_name for alert in high_alerts} >= {
        "security_bypass",
        "backdoor_vulnerability",
    }


def test_hook_manager_captures_activations_shape() -> None:
    """Hook manager should capture layer activations with expected dimensions."""
    torch.manual_seed(19)
    model = ToyCausalLM(vocab_size=32, hidden_dim=16, n_layers=3)
    hook_manager = ActivationHookManager()
    hook_manager.register_hook(model, layer_index=1)

    input_ids = torch.tensor([[1, 2, 3, 4], [4, 3, 2, 1]], dtype=torch.long)
    _ = model(input_ids=input_ids)
    activations = hook_manager.get_activations()
    assert activations.shape == (2, 4, 16)
    hook_manager.clear_hooks()


def test_gradient_attribution_returns_non_zero_scores() -> None:
    """Gradient attribution should produce non-zero SAE feature contributions."""
    torch.manual_seed(23)
    model = ToyCausalLM(vocab_size=48, hidden_dim=20, n_layers=3)
    sae = SparseAutoencoder(input_dim=20, hidden_dim=40, sparsity_coefficient=1e-4)
    with torch.no_grad():
        sae.encoder.bias.fill_(0.2)

    attribution = GradientAttribution()
    input_ids = torch.tensor([[1, 7, 5, 9, 3]], dtype=torch.long)
    scores = attribution.attribute_to_features(
        model=model,
        sae=sae,
        input_ids=input_ids,
        target_token_idx=-1,
        target_layer=1,
    )
    assert len(scores) > 0
    assert any(abs(score) > 0 for score in scores.values())
