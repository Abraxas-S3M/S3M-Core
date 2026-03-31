"""Unit tests for Phase 8 model optimizer."""

from __future__ import annotations

from pathlib import Path

from src.navigation.edge_inference.model_optimizer import ModelOptimizer


def test_initialization_creates_output_directory(tmp_path):
    out = tmp_path / "optimized"
    ModelOptimizer(output_dir=str(out))
    assert out.exists()


def test_list_optimized_models_empty(tmp_path):
    optimizer = ModelOptimizer(output_dir=str(tmp_path))
    assert optimizer.list_optimized_models() == []


def test_estimate_memory_positive(tmp_path):
    dummy = tmp_path / "model.bin"
    dummy.write_bytes(b"\x00" * 256)
    optimizer = ModelOptimizer(output_dir=str(tmp_path / "out"))
    assert optimizer.estimate_memory(str(dummy)) > 0


def test_benchmark_runs_without_loaded_models(tmp_path):
    dummy = tmp_path / "model.onnx"
    dummy.write_bytes(b"\x00" * 512)
    optimizer = ModelOptimizer(output_dir=str(tmp_path / "out"))
    result = optimizer.benchmark(str(dummy), n_iterations=5)
    assert result["avg_latency_ms"] >= 0
    assert result["throughput_fps"] >= 0
