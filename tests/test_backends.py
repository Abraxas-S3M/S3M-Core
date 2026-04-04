"""Unit tests for S3M pluggable inference backends."""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, ".")

from src.llm_core.backends.backend_factory import BackendFactory
from src.llm_core.backends.base_backend import InferenceBackend
from src.llm_core.backends.llama_cpp_backend import LlamaCppBackend
from src.llm_core.backends.onnx_backend import OnnxBackend
from src.llm_core.backends.openvino_backend import OpenVinoBackend


class _DummyBackend(InferenceBackend):
    @property
    def backend_name(self) -> str:
        return "dummy"

    def load(self) -> bool:
        self._loaded = True
        return True

    def unload(self) -> None:
        self._loaded = False

    def generate(
        self,
        prompt: str,
        max_tokens: int = 512,
        temperature: float = 0.7,
        top_p: float = 0.9,
        stop: list[str] | None = None,
    ) -> dict:
        del prompt, max_tokens, temperature, top_p, stop
        return {
            "response": "ok",
            "tokens_generated": 1,
            "prompt_tokens": 1,
            "latency_ms": 1.0,
            "tokens_per_second": 1.0,
        }

    def health_check(self) -> dict:
        return {"backend": "dummy", "loaded": self._loaded}


class _DummyTokenizer:
    def __call__(self, prompt: str, return_tensors: str = "np") -> dict[str, np.ndarray]:
        del prompt, return_tensors
        return {
            "input_ids": np.array([[10, 11]], dtype=np.int64),
            "attention_mask": np.array([[1, 1]], dtype=np.int64),
        }

    def decode(self, token_ids, skip_special_tokens: bool = True) -> str:
        del skip_special_tokens
        arr = np.asarray(token_ids).reshape(-1)
        return " ".join(str(int(x)) for x in arr)


class _DummyInputMeta:
    def __init__(self, name: str) -> None:
        self.name = name


class _DummySession:
    def __init__(self) -> None:
        self.calls = 0

    def get_inputs(self) -> list[_DummyInputMeta]:
        return [_DummyInputMeta("input_ids"), _DummyInputMeta("attention_mask")]

    def get_providers(self) -> list[str]:
        return ["CPUExecutionProvider"]

    def run(self, output_names, model_inputs: dict[str, np.ndarray]) -> list[np.ndarray]:
        del output_names
        self.calls += 1
        seq_len = model_inputs["input_ids"].shape[-1]
        logits = np.zeros((1, seq_len, 32), dtype=np.float32)
        logits[0, -1, self.calls + 2] = 1.0
        return [logits]


class _DummyPort:
    def __init__(self, name: str) -> None:
        self._name = name

    def get_any_name(self) -> str:
        return self._name


class _DummyCompiledModel:
    def __init__(self) -> None:
        self.calls = 0
        self.inputs = [_DummyPort("input_ids"), _DummyPort("attention_mask")]

    def __call__(self, model_inputs: dict[str, np.ndarray]) -> dict[str, np.ndarray]:
        self.calls += 1
        seq_len = model_inputs["input_ids"].shape[-1]
        logits = np.zeros((1, seq_len, 32), dtype=np.float32)
        logits[0, -1, self.calls + 4] = 1.0
        return {"logits": logits}


def test_backend_factory_create_supported_backends() -> None:
    assert isinstance(BackendFactory.create("gguf", "m.gguf", {}), LlamaCppBackend)
    assert isinstance(BackendFactory.create("onnx", "m.onnx", {}), OnnxBackend)
    assert isinstance(BackendFactory.create("openvino", "model.xml", {}), OpenVinoBackend)


def test_backend_factory_raises_for_unknown_backend() -> None:
    with pytest.raises(ValueError):
        BackendFactory.create("tensor_rt", "m.plan", {})


def test_base_backend_estimate_memory_mb(tmp_path: Path) -> None:
    model_path = tmp_path / "model.bin"
    model_path.write_bytes(b"a" * (2 * 1024 * 1024))
    backend = _DummyBackend(str(model_path), {})
    assert backend.estimate_memory_mb() == pytest.approx(2.0, rel=1e-3)


def test_llama_cpp_load_sets_thread_count_for_cpu(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    model_path = tmp_path / "model.gguf"
    model_path.write_bytes(b"gguf")

    class FakeLlama:
        def __init__(self, **kwargs) -> None:
            self.kwargs = kwargs

    import src.llm_core.backends.llama_cpp_backend as module

    monkeypatch.setattr(module, "LLAMA_CPP_AVAILABLE", True)
    monkeypatch.setattr(module, "Llama", FakeLlama)
    monkeypatch.setattr(module.os, "cpu_count", lambda: 8)

    backend = module.LlamaCppBackend(str(model_path), {"n_gpu_layers": 0, "n_ctx": 1024})
    assert backend.load() is True
    assert backend.n_threads == 7
    assert backend.is_loaded is True


def test_llama_cpp_generate_uses_chat_template(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    model_path = tmp_path / "model.gguf"
    model_path.write_bytes(b"gguf")

    class FakeLlama:
        def __init__(self, **kwargs) -> None:
            del kwargs
            self.last_prompt = ""

        def __call__(self, prompt: str, **kwargs) -> dict:
            del kwargs
            self.last_prompt = prompt
            return {"choices": [{"text": "ack"}], "usage": {"completion_tokens": 1, "prompt_tokens": 3}}

    import src.llm_core.backends.llama_cpp_backend as module

    monkeypatch.setattr(module, "LLAMA_CPP_AVAILABLE", True)
    monkeypatch.setattr(module, "Llama", FakeLlama)

    backend = module.LlamaCppBackend(str(model_path), {})
    assert backend.load() is True
    result = backend.generate("status report", max_tokens=8)
    assert result["response"] == "ack"
    assert backend._llm.last_prompt == "<|user|>\nstatus report\n<|assistant|>\n"


def test_onnx_load_returns_false_when_runtime_missing(monkeypatch: pytest.MonkeyPatch) -> None:
    import src.llm_core.backends.onnx_backend as module

    monkeypatch.setattr(module, "ONNX_AVAILABLE", False)
    monkeypatch.setattr(module, "ort", None)

    backend = module.OnnxBackend("model.onnx", {})
    assert backend.load() is False


def test_onnx_generate_returns_expected_telemetry() -> None:
    backend = OnnxBackend("model.onnx", {})
    backend._session = _DummySession()
    backend._tokenizer = _DummyTokenizer()
    backend._loaded = True

    result = backend.generate("edge prompt", max_tokens=2)
    assert result["tokens_generated"] == 2
    assert result["prompt_tokens"] == 2
    assert isinstance(result["response"], str)
    assert result["latency_ms"] >= 0.0


def test_openvino_load_returns_false_without_transformers(monkeypatch: pytest.MonkeyPatch) -> None:
    import src.llm_core.backends.openvino_backend as module

    monkeypatch.setattr(module, "TRANSFORMERS_AVAILABLE", False)
    monkeypatch.setattr(module, "AutoTokenizer", None)

    backend = module.OpenVinoBackend("model.xml", {})
    assert backend.load() is False


def test_openvino_raw_generate_cycle() -> None:
    backend = OpenVinoBackend("model.xml", {})
    backend._compiled_model = _DummyCompiledModel()
    backend._tokenizer = _DummyTokenizer()
    backend._loaded = True

    result = backend.generate("tactical prompt", max_tokens=2)
    assert result["tokens_generated"] == 2
    assert result["prompt_tokens"] == 2
    assert isinstance(result["response"], str)
    assert result["tokens_per_second"] >= 0.0
