"""Unit tests for CPU adapter tuner quantization workflow."""

from __future__ import annotations

import pytest

from src.training.cpu_adaptation.adapter_tuner import AdapterConfig, CPUAdapterTuner

try:
    import torch

    TORCH_AVAILABLE = True
except Exception:  # pragma: no cover - optional runtime
    torch = None  # type: ignore[assignment]
    TORCH_AVAILABLE = False


@pytest.mark.skipif(not TORCH_AVAILABLE, reason="torch not installed")
def test_prepare_and_train_cpu_fallback_path() -> None:
    tuner = CPUAdapterTuner(
        base_model_path="missing-local-model",
        config=AdapterConfig(
            max_steps=2,
            gradient_accumulation_steps=1,
            max_memory_mb=8192,
            use_qat=True,
            target_modules=[],
        ),
    )
    assert tuner.prepare() is True

    result = tuner.train(
        [
            {"instruction": "observe", "input": "grid", "output": "ack"},
            {"instruction": "route", "input": "safe lane", "output": "confirmed"},
        ]
    )
    assert result.success is True
    assert result.steps_completed == 2
    assert result.final_loss >= 0.0
    assert result.precision_used in {"fp32", "bf16"}
    assert result.unique_weight_values_per_layer


@pytest.mark.skipif(not TORCH_AVAILABLE, reason="torch not installed")
def test_memory_budget_enforcement(monkeypatch) -> None:
    tuner = CPUAdapterTuner(base_model_path="dummy", config=AdapterConfig(max_memory_mb=1))
    monkeypatch.setattr(tuner, "_current_rss_mb", lambda: 2.5)
    assert tuner._check_memory_budget() is False
    with pytest.raises(MemoryError):
        tuner._enforce_memory_budget()


@pytest.mark.skipif(not TORCH_AVAILABLE, reason="torch not installed")
def test_legacy_train_adapter_interface() -> None:
    tuner = CPUAdapterTuner(
        base_model_path="dummy",
        config=AdapterConfig(max_steps=1, gradient_accumulation_steps=1, max_memory_mb=8192),
    )
    result = tuner.train_adapter("phi3-medium", [{"prompt": "brief", "response": "ok"}], epochs=1)
    assert result.success is True
    assert result.model_id == "phi3-medium"
    assert result.epochs == 1
