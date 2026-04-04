"""
S3M 4-Bit Quantization-Aware Training Primitives
Research basis: 'True 4-Bit Quantized CNN Training on CPU' (arXiv:2603.13931, Mar 2026)

Core innovation: tanh-based soft weight clipping prevents gradient explosion during
aggressive 4-bit quantization, achieving full-precision parity on commodity CPUs.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Dict, Optional, Tuple

try:
    import torch
    import torch.nn as nn
    import torch.nn.functional as F

    TORCH_AVAILABLE = True
except Exception:  # pragma: no cover - optional dependency guard
    torch = None  # type: ignore[assignment]
    nn = None  # type: ignore[assignment]
    F = None  # type: ignore[assignment]
    TORCH_AVAILABLE = False


@dataclass
class QuantConfig:
    """Configuration for 4-bit quantization-aware training."""

    num_bits: int = 4
    symmetric: bool = True
    per_layer_scaling: bool = True
    tanh_clipping_enabled: bool = True
    tanh_scale: float = 3.0
    gradient_clip_norm: float = 0.5
    num_discrete_values: int = 15


class TanhSoftClipper:
    """
    Apply tanh-based soft weight clipping after each optimizer step.

    From research: This non-linear transformation provides:
    1. Smooth gradient preservation (unlike hard clipping which zeros gradients)
    2. Natural weight regularization toward moderate values
    3. Synergy with per-layer dynamic scaling
    4. Prevention of quantization overflow

    Usage:
        clipper = TanhSoftClipper(scale=3.0)
        # In training loop, after optimizer.step():
        clipper.apply(model)
    """

    def __init__(self, scale: float = 3.0):
        if scale <= 0.0:
            raise ValueError("scale must be > 0")
        self.scale = float(scale)

    def apply(self, model: nn.Module) -> None:
        """Apply tanh soft clipping to all trainable parameters in-place.
        W = scale * tanh(W / scale)
        """
        if not TORCH_AVAILABLE or torch is None:
            raise RuntimeError("torch is required for TanhSoftClipper")
        with torch.no_grad():
            for param in model.parameters():
                if param.requires_grad:
                    param.copy_(self.scale * torch.tanh(param / self.scale))

    def apply_to_named(self, model: nn.Module, target_modules: Optional[list[str]] = None) -> Dict[str, bool]:
        """Apply only to specific named modules (e.g., q_proj, v_proj for LoRA).
        Returns dict of {param_name: was_clipped}.
        """
        if not TORCH_AVAILABLE or torch is None:
            raise RuntimeError("torch is required for TanhSoftClipper")
        targets = set(target_modules or [])
        clipped: Dict[str, bool] = {}
        with torch.no_grad():
            for name, param in model.named_parameters():
                if not param.requires_grad:
                    clipped[name] = False
                    continue
                should_clip = not targets or any(target in name for target in targets)
                if should_clip:
                    param.copy_(self.scale * torch.tanh(param / self.scale))
                clipped[name] = should_clip
        return clipped


class SymmetricQuantizer:
    """
    Symmetric 4-bit quantization with dynamic per-layer scaling.

    Maps weights to exactly 15 discrete values in [-7, 7] * scale.
    Uses straight-through estimator for backpropagation.

    Forward pass: W_q = clamp(round(W / s), -7, 7) * s
    Backward pass: gradients pass through unchanged (STE)
    where s = max(|W|) / 7 per layer
    """

    def __init__(self, config: QuantConfig):
        if not TORCH_AVAILABLE or torch is None:
            raise RuntimeError("torch is required for SymmetricQuantizer")
        self.config = config
        self.half_range = (2 ** (config.num_bits - 1)) - 1  # 7 for 4-bit

    def quantize_weights(self, weights: torch.Tensor) -> Tuple[torch.Tensor, float]:
        """Quantize weights to discrete levels.
        Returns: (quantized_weights, scale_factor)
        """
        c = weights.detach().abs().max().item()
        if c == 0.0:
            return weights.detach().clone(), 1.0
        s = float(c / self.half_range)
        w_int = torch.clamp(torch.round(weights / s), -self.half_range, self.half_range)
        w_q = w_int * s
        return w_q, s

    def forward_with_ste(self, weights: torch.Tensor) -> torch.Tensor:
        """Quantize for forward pass using straight-through estimator.
        The quantized values are used in forward, but gradients flow to
        the full-precision weights unchanged.

        Implementation: W_ste = W + (W_q - W).detach()
        This makes the forward use W_q but backward treats it as W.
        """
        w_q, _ = self.quantize_weights(weights)
        return weights + (w_q - weights).detach()

    def count_unique_values(self, weights: torch.Tensor) -> int:
        """Verify the quantized tensor has exactly num_discrete_values unique values.
        Used for validation/testing.
        """
        w_q, _ = self.quantize_weights(weights)
        return int(torch.unique(w_q.detach()).numel())


class QuantAwareLinear(nn.Module):
    """
    Drop-in replacement for nn.Linear with 4-bit QAT.

    Full-precision weights are maintained for gradient updates.
    Forward pass uses quantized weights via STE.
    Batch normalization is recommended after this layer.
    """

    def __init__(
        self,
        in_features: int,
        out_features: int,
        bias: bool = True,
        config: Optional[QuantConfig] = None,
    ) -> None:
        if not TORCH_AVAILABLE or torch is None or nn is None:
            raise RuntimeError("torch is required for QuantAwareLinear")
        super().__init__()
        self.in_features = int(in_features)
        self.out_features = int(out_features)
        self.config = config or QuantConfig()
        self.quantizer = SymmetricQuantizer(self.config)
        self.weight = nn.Parameter(torch.empty((self.out_features, self.in_features)))
        if bias:
            self.bias = nn.Parameter(torch.empty(self.out_features))
        else:
            self.register_parameter("bias", None)
        self.reset_parameters()

    def reset_parameters(self) -> None:
        nn.init.kaiming_uniform_(self.weight, a=math.sqrt(5))
        if self.bias is not None:
            fan_in, _ = nn.init._calculate_fan_in_and_fan_out(self.weight)
            bound = 1.0 / math.sqrt(fan_in) if fan_in > 0 else 0.0
            nn.init.uniform_(self.bias, -bound, bound)

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        """Forward with quantized weights via straight-through estimator."""
        w_q = self.quantizer.forward_with_ste(self.weight)
        return F.linear(x, w_q, self.bias)


class QuantAwareConv2d(nn.Module):
    """Drop-in replacement for nn.Conv2d with 4-bit QAT. Same STE approach."""

    def __init__(
        self,
        in_channels: int,
        out_channels: int,
        kernel_size: int | tuple[int, int],
        stride: int | tuple[int, int] = 1,
        padding: int | tuple[int, int] = 0,
        dilation: int | tuple[int, int] = 1,
        groups: int = 1,
        bias: bool = True,
        config: Optional[QuantConfig] = None,
    ) -> None:
        if not TORCH_AVAILABLE or torch is None or nn is None:
            raise RuntimeError("torch is required for QuantAwareConv2d")
        super().__init__()
        self.in_channels = int(in_channels)
        self.out_channels = int(out_channels)
        self.kernel_size = kernel_size if isinstance(kernel_size, tuple) else (kernel_size, kernel_size)
        self.stride = stride if isinstance(stride, tuple) else (stride, stride)
        self.padding = padding if isinstance(padding, tuple) else (padding, padding)
        self.dilation = dilation if isinstance(dilation, tuple) else (dilation, dilation)
        self.groups = int(groups)
        self.config = config or QuantConfig()
        self.quantizer = SymmetricQuantizer(self.config)

        weight_shape = (
            self.out_channels,
            self.in_channels // self.groups,
            self.kernel_size[0],
            self.kernel_size[1],
        )
        self.weight = nn.Parameter(torch.empty(weight_shape))
        if bias:
            self.bias = nn.Parameter(torch.empty(self.out_channels))
        else:
            self.register_parameter("bias", None)
        self.reset_parameters()

    def reset_parameters(self) -> None:
        nn.init.kaiming_uniform_(self.weight, a=math.sqrt(5))
        if self.bias is not None:
            fan_in, _ = nn.init._calculate_fan_in_and_fan_out(self.weight)
            bound = 1.0 / math.sqrt(fan_in) if fan_in > 0 else 0.0
            nn.init.uniform_(self.bias, -bound, bound)

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        w_q = self.quantizer.forward_with_ste(self.weight)
        return F.conv2d(
            x,
            w_q,
            self.bias,
            stride=self.stride,
            padding=self.padding,
            dilation=self.dilation,
            groups=self.groups,
        )


class QuantAwareAdamW(torch.optim.AdamW):
    """
    Custom AdamW that integrates tanh soft clipping after each step.

    From research training procedure:
    1. Standard AdamW weight decay (5e-4)
    2. Gradient clipping (max norm = 0.5)
    3. Tanh soft weight clipping (W = 3.0 * tanh(W / 3.0)) applied post-update

    This optimizer wraps the full research-validated training procedure into
    a single optimizer class.
    """

    def __init__(
        self,
        params,
        lr: float = 2e-4,
        weight_decay: float = 5e-4,
        gradient_clip_norm: float = 0.5,
        tanh_scale: float = 3.0,
        **kwargs,
    ) -> None:
        if not TORCH_AVAILABLE or torch is None or nn is None:
            raise RuntimeError("torch is required for QuantAwareAdamW")
        super().__init__(params, lr=lr, weight_decay=weight_decay, **kwargs)
        if gradient_clip_norm <= 0.0:
            raise ValueError("gradient_clip_norm must be > 0")
        if tanh_scale <= 0.0:
            raise ValueError("tanh_scale must be > 0")
        self.gradient_clip_norm = float(gradient_clip_norm)
        self.tanh_scale = float(tanh_scale)

    def step(self, closure=None):
        """
        1. Clip gradients by norm
        2. Standard AdamW step
        3. Apply tanh soft clipping to all parameters
        """
        grad_params = [p for group in self.param_groups for p in group["params"] if p.grad is not None]
        if grad_params:
            nn.utils.clip_grad_norm_(grad_params, max_norm=self.gradient_clip_norm)

        loss = super().step(closure=closure)
        with torch.no_grad():
            for group in self.param_groups:
                for param in group["params"]:
                    if param.requires_grad:
                        param.copy_(self.tanh_scale * torch.tanh(param / self.tanh_scale))
        return loss
