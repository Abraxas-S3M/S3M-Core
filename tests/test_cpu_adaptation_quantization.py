"""Unit tests for CPU QAT primitives used in edge adaptation."""

from __future__ import annotations

import pytest

from src.training.cpu_adaptation.quantization import (
    QuantAwareAdamW,
    QuantConfig,
    SymmetricQuantizer,
    TanhSoftClipper,
)

try:
    import torch
    import torch.nn as nn

    TORCH_AVAILABLE = True
except Exception:  # pragma: no cover - optional runtime
    torch = None  # type: ignore[assignment]
    nn = None  # type: ignore[assignment]
    TORCH_AVAILABLE = False


@pytest.mark.skipif(not TORCH_AVAILABLE, reason="torch not installed")
def test_symmetric_quantizer_hits_15_discrete_levels() -> None:
    quantizer = SymmetricQuantizer(QuantConfig())
    weights = torch.linspace(-7.0, 7.0, steps=15)
    quantized, scale = quantizer.quantize_weights(weights)
    assert scale == pytest.approx(1.0)
    assert quantizer.count_unique_values(weights) == 15
    assert torch.allclose(weights, quantized, atol=1e-6)


@pytest.mark.skipif(not TORCH_AVAILABLE, reason="torch not installed")
def test_forward_with_ste_preserves_gradients() -> None:
    quantizer = SymmetricQuantizer(QuantConfig())
    weights = torch.tensor([[-0.9, 0.1, 1.4]], dtype=torch.float32, requires_grad=True)
    out = quantizer.forward_with_ste(weights).sum()
    out.backward()
    assert weights.grad is not None
    assert torch.allclose(weights.grad, torch.ones_like(weights))


@pytest.mark.skipif(not TORCH_AVAILABLE, reason="torch not installed")
def test_quant_aware_adamw_applies_post_step_tanh_clipping() -> None:
    layer = nn.Linear(4, 4, bias=False)
    with torch.no_grad():
        layer.weight.fill_(25.0)

    optimizer = QuantAwareAdamW(
        layer.parameters(),
        lr=0.0,
        weight_decay=0.0,
        gradient_clip_norm=0.5,
        tanh_scale=3.0,
    )
    loss = layer(torch.ones((1, 4))).sum()
    loss.backward()
    optimizer.step()
    assert float(layer.weight.detach().abs().max().item()) <= 3.0 + 1e-6


@pytest.mark.skipif(not TORCH_AVAILABLE, reason="torch not installed")
def test_tanh_soft_clipper_named_filter() -> None:
    model = nn.Sequential(nn.Linear(2, 2), nn.Linear(2, 2))
    with torch.no_grad():
        for param in model.parameters():
            param.fill_(20.0)

    clipper = TanhSoftClipper(scale=3.0)
    clipped = clipper.apply_to_named(model, target_modules=["0"])
    assert any(name.startswith("0.") and was for name, was in clipped.items())
    assert all((name.startswith("0.") or not was) for name, was in clipped.items())
