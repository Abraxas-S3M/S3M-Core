"""Tests for S3M Inference Engine - runs without model files"""

import sys
sys.path.insert(0, ".")

from src.llm_core.inference_engine import InferenceEngine, InferenceResult, LLAMA_CPP_AVAILABLE
from src.llm_core.engine_registry import EngineID


def test_engine_initialization():
    engine = InferenceEngine(EngineID.PHI3_MEDIUM)
    assert engine.engine_id == EngineID.PHI3_MEDIUM
    assert engine.loaded == False
    assert engine.config.name == "Phi-3 Medium"
    print("PASS: Engine initializes correctly")


def test_health_check():
    engine = InferenceEngine(EngineID.GROK1)
    health = engine.health_check()
    assert health["engine"] == "grok1-314b"
    assert health["loaded"] == False
    assert "model_file_exists" in health
    assert "llama_cpp_available" in health
    print("PASS: Health check returns correct structure")


def test_generate_without_model():
    engine = InferenceEngine(EngineID.MIXTRAL)
    result = engine.generate("test prompt")
    assert "[ERROR]" in result.response
    assert result.tokens_generated == 0
    print("PASS: Generate returns error when model not loaded")


def test_all_engines_initialize():
    for eid in EngineID:
        engine = InferenceEngine(eid)
        assert engine.engine_id == eid
        assert engine.config is not None
    print("PASS: All four engines initialize")


def test_result_to_dict():
    result = InferenceResult(
        engine_id=EngineID.PHI3_MEDIUM,
        prompt="test",
        response="test response",
        tokens_generated=10,
        prompt_tokens=5,
        latency_ms=100.0,
        tokens_per_second=100.0,
        model_name="Phi-3 Medium",
    )
    d = result.to_dict()
    assert d["engine"] == "phi3-medium"
    assert d["tokens_generated"] == 10
    print("PASS: InferenceResult serializes to dict")


if __name__ == "__main__":
    test_engine_initialization()
    test_health_check()
    test_generate_without_model()
    test_all_engines_initialize()
    test_result_to_dict()
    print(f"\nllama-cpp-python available: {LLAMA_CPP_AVAILABLE}")
    print("All inference engine tests passed")
