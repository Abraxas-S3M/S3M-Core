"""
S3M Llama.cpp Backend
Provides GGUF inference for tactical edge nodes running air-gapped CPU/GPU blends.
"""

from __future__ import annotations

from pathlib import Path
from time import perf_counter
from typing import Any
import logging
import os

from .base_backend import InferenceBackend

try:
    from llama_cpp import Llama

    LLAMA_CPP_AVAILABLE = True
except ImportError:
    Llama = None
    LLAMA_CPP_AVAILABLE = False

logger = logging.getLogger("s3m.backends.llama_cpp")


class LlamaCppBackend(InferenceBackend):
    """Inference backend for GGUF models via llama-cpp-python."""

    def __init__(self, model_path: str, config: dict[str, Any]) -> None:
        super().__init__(model_path=model_path, config=config)
        self.n_gpu_layers = int(config.get("n_gpu_layers", 0))
        self.n_ctx = int(config.get("n_ctx", 4096))
        self.n_threads = config.get("n_threads")
        self._llm: Any = None

    @property
    def backend_name(self) -> str:
        return "llama_cpp"

    def load(self) -> bool:
        if not LLAMA_CPP_AVAILABLE or Llama is None:
            logger.warning("llama-cpp-python is not installed; GGUF backend unavailable")
            return False

        model_file = Path(self.model_path)
        if not model_file.exists():
            logger.error("GGUF model file not found: %s", model_file)
            return False

        if self.n_threads is None and self.n_gpu_layers == 0:
            cpu_count = os.cpu_count() or 1
            self.n_threads = max(1, cpu_count - 1)

        try:
            self._llm = Llama(
                model_path=str(model_file),
                n_gpu_layers=self.n_gpu_layers,
                n_ctx=self.n_ctx,
                n_threads=self.n_threads,
                verbose=False,
            )
            self._loaded = True
            return True
        except Exception:
            logger.exception("Failed to load llama.cpp model: %s", model_file)
            self._loaded = False
            return False

    def unload(self) -> None:
        if self._llm is not None:
            del self._llm
            self._llm = None
        self._loaded = False

    def generate(
        self,
        prompt: str,
        max_tokens: int = 512,
        temperature: float = 0.7,
        top_p: float = 0.9,
        stop: list[str] | None = None,
    ) -> dict[str, Any]:
        if not self._loaded or self._llm is None:
            return self._error_result("Model not loaded")

        full_prompt = f"<|user|>\n{prompt}\n<|assistant|>\n"
        stop_tokens = stop or ["<|end|>", "<|user|>"]

        try:
            start = perf_counter()
            output = self._llm(
                full_prompt,
                max_tokens=max_tokens,
                temperature=temperature,
                top_p=top_p,
                stop=stop_tokens,
                echo=False,
            )
            latency_ms = (perf_counter() - start) * 1000.0

            response_text = str(output["choices"][0]["text"]).strip()
            usage = output.get("usage", {})
            tokens_generated = int(usage.get("completion_tokens", 0))
            prompt_tokens = int(usage.get("prompt_tokens", 0))
            tokens_per_second = (tokens_generated / (latency_ms / 1000.0)) if latency_ms > 0 else 0.0

            return {
                "response": response_text,
                "tokens_generated": tokens_generated,
                "prompt_tokens": prompt_tokens,
                "latency_ms": latency_ms,
                "tokens_per_second": tokens_per_second,
            }
        except Exception:
            logger.exception("llama.cpp generation failed")
            return self._error_result("Inference failed")

    def health_check(self) -> dict[str, Any]:
        return {
            "backend": self.backend_name,
            "loaded": self._loaded,
            "llama_cpp_available": LLAMA_CPP_AVAILABLE,
            "gpu_layers": self.n_gpu_layers,
            "thread_count": self.n_threads,
            "model_path": self.model_path,
            "model_exists": Path(self.model_path).exists(),
        }

    @staticmethod
    def _error_result(message: str) -> dict[str, Any]:
        return {
            "response": f"[ERROR] {message}",
            "tokens_generated": 0,
            "prompt_tokens": 0,
            "latency_ms": 0.0,
            "tokens_per_second": 0.0,
        }
