"""Unit tests for sparse MoE tactical fallback layer."""

from __future__ import annotations

import numpy as np
import pytest

from src.training.cpu_adaptation.sparse_moe import SparseMoELayer


def test_route_returns_expected_top_k_shape() -> None:
    layer = SparseMoELayer(input_dim=4, num_experts=5, top_k=2, seed=3)
    idx, weights = layer.route([0.4, 0.2, 0.1, 0.3])
    assert idx.shape == (2,)
    assert weights.shape == (2,)
    assert float(np.sum(weights)) == pytest.approx(1.0, abs=1e-9)


def test_forward_returns_input_dimension() -> None:
    layer = SparseMoELayer(input_dim=3, num_experts=4, top_k=2)
    output = layer.forward([1.0, -0.5, 0.25])
    assert output.shape == (3,)


def test_call_alias_matches_forward() -> None:
    layer = SparseMoELayer(input_dim=3, num_experts=4, top_k=2, seed=8)
    inp = [0.2, 0.3, 0.4]
    assert np.allclose(layer(inp), layer.forward(inp))

