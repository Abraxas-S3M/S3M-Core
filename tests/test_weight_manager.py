"""Tests for weight manager command generation and storage reporting."""

from pathlib import Path

import pytest

from src.llm_core.engine_registry import EngineID
from src.llm_core.model_registry import ModelRegistry
from src.llm_core.weight_manager import WeightManager


@pytest.fixture
def weight_manager(tmp_path):
    """Create a weight manager instance with an isolated registry file."""
    registry_file = tmp_path / "model_registry.json"
    model_registry = ModelRegistry(str(registry_file))
    return WeightManager(model_registry=model_registry)


def test_pull_from_huggingface_returns_updated_commands(weight_manager):
    """Updated model repos are returned for all engines."""
    assert (
        weight_manager.pull_from_huggingface(EngineID.PHI3)
        == "huggingface-cli download microsoft/Phi-3-medium-4k-instruct --local-dir models/phi3-medium/"
    )
    assert (
        weight_manager.pull_from_huggingface(EngineID.GROK)
        == "huggingface-cli download xai-org/grok-1 --repo-type model --include 'ckpt-0/*' --local-dir models/grok1/"
    )
    assert (
        weight_manager.pull_from_huggingface(EngineID.MISTRAL)
        == "huggingface-cli download mistralai/Mixtral-8x7B-Instruct-v0.1 --local-dir models/mixtral/"
    )
    assert (
        weight_manager.pull_from_huggingface(EngineID.ALLAM)
        == "huggingface-cli download humain-ai/ALLaM-7B-Instruct-preview --local-dir models/allam/"
    )


def test_pull_quantized_gguf_returns_expected_commands(weight_manager):
    """Pre-quantized command map is complete and explicit."""
    assert "bartowski/Phi-3-medium-4k-instruct-GGUF" in weight_manager.pull_quantized_gguf(EngineID.PHI3)
    assert "TheBloke/Mixtral-8x7B-Instruct-v0.1-GGUF" in weight_manager.pull_quantized_gguf(EngineID.MISTRAL)
    assert (
        weight_manager.pull_quantized_gguf(EngineID.GROK)
        == "No pre-quantized GGUF available. Must convert from fp16 checkpoints."
    )
    assert (
        weight_manager.pull_quantized_gguf(EngineID.ALLAM)
        == "No pre-quantized GGUF available. Must convert from fp16."
    )


def test_get_storage_requirements_returns_totals(weight_manager):
    """Storage report includes all engines and deterministic totals."""
    requirements = weight_manager.get_storage_requirements()
    assert set(requirements) == {"phi3_medium", "grok1", "mixtral", "allam", "totals"}
    assert requirements["totals"]["fp16_gb"] == pytest.approx(768.0)
    assert requirements["totals"]["q4_gb"] == pytest.approx(400.0)


def test_status_report_includes_size_tier_and_vault_flags(weight_manager):
    """Status report surfaces planning fields needed by operators."""
    report = weight_manager.get_status_report()
    assert "FP16 size GB:" in report
    assert "Q4 size GB:" in report
    assert "Training tier:" in report
    assert "Vault sync:" in report


def test_pull_from_huggingface_creates_target_directories(weight_manager, monkeypatch, tmp_path):
    """Model pull command generation prepares local model directories."""
    monkeypatch.chdir(tmp_path)
    weight_manager.pull_from_huggingface(EngineID.PHI3)
    weight_manager.pull_from_huggingface(EngineID.GROK)
    weight_manager.pull_from_huggingface(EngineID.MISTRAL)
    weight_manager.pull_from_huggingface(EngineID.ALLAM)
    assert Path("models/phi3-medium").exists()
    assert Path("models/grok1").exists()
    assert Path("models/mixtral").exists()
    assert Path("models/allam").exists()
