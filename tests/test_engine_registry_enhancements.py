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
    assert any(cfg.engine_id == EngineID.PHI3 for cfg in fast_engines)


def test_get_capability_score():
    """Validate domain confidence scoring for mission-domain matching."""
    registry = EngineRegistry()
    phi3_tactical = registry.get_capability_score(EngineID.PHI3, TaskDomain.TACTICAL)
    assert phi3_tactical > 0.8


def test_get_total_memory_required():
    """Validate aggregate VRAM planning across selected edge engines."""
    registry = EngineRegistry()
    all_engines = list(EngineID)
    total = registry.get_total_memory_required(all_engines)
    assert 18 < total < 20


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
