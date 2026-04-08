import pytest

from src.llm_core.engine_registry import (
    ENGINE_CONFIGS,
    EngineID,
    EngineRegistry,
    TaskDomain,
)


def test_engine_config_has_new_metadata():
    """Verify all engines expose metadata needed for tactical routing."""
    for engine_id in EngineID:
        config = ENGINE_CONFIGS[engine_id]
        assert config.latency_tier in ["fast", "medium", "slow"]
        assert config.inference_latency_ms > 0
        assert config.throughput_tok_s > 0
        assert config.memory_footprint_gb > 0
        assert 0.0 <= config.confidence_prior <= 1.0
        assert config.capabilities is not None


def test_get_engines_by_tier():
    """Ensure low-latency engines can be selected for urgent decisions."""
    registry = EngineRegistry()
    fast_engines = registry.get_engines_by_tier("fast")
    assert any(cfg.engine_id == EngineID.PHI3_MEDIUM for cfg in fast_engines)


def test_get_capability_score():
    """Validate domain confidence scoring for mission-domain matching."""
    registry = EngineRegistry()
    phi3_tactical = registry.get_capability_score(EngineID.PHI3_MEDIUM, TaskDomain.TACTICAL)
    assert phi3_tactical > 0.8


def test_get_total_memory_required():
    """Validate aggregate VRAM planning across selected edge engines."""
    registry = EngineRegistry()
    all_engines = list(EngineID)
    total = registry.get_total_memory_required(all_engines)
    assert 128 <= total <= 130


def test_engine_training_metadata_targets():
    """Verify training-aware engine metadata for tactical edge adaptation."""
    phi3 = ENGINE_CONFIGS[EngineID.PHI3_MEDIUM]
    assert phi3.adapter_tuning_allowed is True
    assert phi3.adapter_tuning_min_ram_gb == 10.0
    assert phi3.preferred_student_model is None
    assert phi3.cpu_inference_tok_s_target == 10.0
    assert phi3.cpu_inference_ram_mb == 8500

    grok = ENGINE_CONFIGS[EngineID.GROK1]
    assert grok.adapter_tuning_allowed is False
    assert grok.adapter_tuning_min_ram_gb == 85.0
    assert grok.preferred_student_model == "phi3-medium"
    assert grok.cpu_inference_tok_s_target == 1.0
    assert grok.cpu_inference_ram_mb == 80000

    mistral = ENGINE_CONFIGS[EngineID.MIXTRAL]
    assert mistral.adapter_tuning_allowed is False
    assert mistral.adapter_tuning_min_ram_gb == 28.0
    assert mistral.preferred_student_model == "phi3-medium"
    assert mistral.cpu_inference_tok_s_target == 3.0
    assert mistral.cpu_inference_ram_mb == 26000

    allam = ENGINE_CONFIGS[EngineID.ALLAM]
    assert allam.adapter_tuning_allowed is True
    assert allam.adapter_tuning_min_ram_gb == 5.0
    assert allam.preferred_student_model == "phi3-medium"
    assert allam.cpu_training_precision_default == "bf16_mixed"
    assert allam.cpu_inference_tok_s_target == 7.0
    assert allam.cpu_inference_ram_mb == 4100


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
