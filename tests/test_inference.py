"""Unit tests for S3M LLM inference module"""
import pytest
from src.llm_core.inference import S3MInference

def test_inference_init():
    engine = S3MInference()
    assert engine.model_path == "models/phi-3-mini-q4_k_m.gguf"

def test_generate_returns_string():
    engine = S3MInference()
    result = engine.generate("What is the threat level?")
    assert isinstance(result, str)
