"""Unit tests for edge inference engine backend fallback behavior."""

from src.navigation.edge_inference.inference_engine import EdgeInferenceEngine


def test_backend_detection_and_health():
    engine = EdgeInferenceEngine()
    assert engine.backend_name in {"tensorrt", "onnxruntime", "pytorch", "none"}
    health = engine.health_check()
    assert "backend" in health
    assert "models_loaded" in health


def test_predict_without_loaded_model_raises():
    engine = EdgeInferenceEngine()
    try:
        engine.predict("unknown", [1, 2, 3])
        assert False, "Expected ValueError for unknown model"
    except ValueError:
        assert True


def test_memory_usage_zero_without_models():
    engine = EdgeInferenceEngine()
    assert engine.get_memory_usage() == 0.0
