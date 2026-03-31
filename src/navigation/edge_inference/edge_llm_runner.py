"""Edge LLM runner for on-device tactical reasoning on Jetson platforms."""

from __future__ import annotations

import os
import time
from typing import Any, Dict, Optional

from src.navigation.models import ModelPrecision


class EdgeLLMRunner:
    """Runs LLM inference on-device for comms-denied tactical operations.

    Military context:
    Local LLM execution allows squads and autonomous assets to reason and
    re-plan even when satellite and RF links are denied by adversary action.
    """

    def __init__(self, model_path: Optional[str] = None, max_memory_mb: float = 8000) -> None:
        if not isinstance(max_memory_mb, (int, float)) or float(max_memory_mb) <= 0:
            raise ValueError("max_memory_mb must be positive")
        self.max_memory_mb = float(max_memory_mb)
        self.model_path = model_path or self._discover_gguf_model()
        self.backend = "stub"
        self.loaded = False
        self._engine: Any = None
        self._model_memory_mb = 0.0
        self._total_inferences = 0
        self._total_tokens = 0
        self._total_latency_ms = 0.0

    @staticmethod
    def _discover_gguf_model() -> Optional[str]:
        model_dir = "models"
        if not os.path.isdir(model_dir):
            return None
        candidates = []
        for item in os.listdir(model_dir):
            path = os.path.join(model_dir, item)
            if os.path.isfile(path) and item.lower().endswith(".gguf"):
                candidates.append(path)
        candidates.sort()
        return candidates[0] if candidates else None

    @staticmethod
    def estimate_memory(model_path: str) -> float:
        if not isinstance(model_path, str) or not model_path.strip():
            raise ValueError("model_path must be a non-empty string")
        if not os.path.exists(model_path):
            return 512.0
        size_mb = max(1.0, os.path.getsize(model_path) / (1024.0 * 1024.0))
        ext = os.path.splitext(model_path)[1].lower()
        if ext in {".engine", ".trt"}:
            return size_mb * 1.3
        if ext == ".gguf":
            lower_name = os.path.basename(model_path).lower()
            if "q4" in lower_name:
                return size_mb * 1.2
            if "q8" in lower_name:
                return size_mb * 1.8
            return size_mb * 1.5
        return size_mb * 2.0

    def load(self, model_path: Optional[str] = None, n_gpu_layers: int = -1, n_ctx: int = 2048) -> bool:
        if model_path is not None:
            self.model_path = model_path
        if self.model_path is None:
            self.backend = "stub"
            self.loaded = False
            return False
        self._model_memory_mb = self.estimate_memory(self.model_path)
        if self._model_memory_mb > self.max_memory_mb:
            self.backend = "stub"
            self.loaded = False
            return False

        path = self.model_path
        ext = os.path.splitext(path)[1].lower()

        if ext in {".engine", ".trt"}:
            try:
                import tensorrt as trt  # type: ignore

                runtime = trt.Runtime(trt.Logger(trt.Logger.WARNING))
                with open(path, "rb") as handle:
                    engine_blob = handle.read()
                engine = runtime.deserialize_cuda_engine(engine_blob)
                if engine is not None:
                    self._engine = engine
                    self.backend = "tensorrt_llm"
                    self.loaded = True
                    return True
            except Exception:
                pass

        if ext == ".gguf":
            try:
                from llama_cpp import Llama  # type: ignore

                self._engine = Llama(model_path=path, n_gpu_layers=n_gpu_layers, n_ctx=n_ctx, verbose=False)
                self.backend = "llama_cpp"
                self.loaded = True
                return True
            except Exception:
                pass

        self._engine = None
        self.backend = "stub"
        self.loaded = False
        return False

    def generate(self, prompt: str, max_tokens: int = 256, temperature: float = 0.7) -> Dict[str, Any]:
        if not isinstance(prompt, str) or not prompt.strip():
            raise ValueError("prompt must be a non-empty string")
        if not isinstance(max_tokens, int) or max_tokens <= 0:
            raise ValueError("max_tokens must be positive integer")
        if not isinstance(temperature, (int, float)) or float(temperature) < 0:
            raise ValueError("temperature must be non-negative")
        start = time.perf_counter()

        if self.backend == "llama_cpp" and self._engine is not None:
            try:
                result = self._engine(prompt, max_tokens=max_tokens, temperature=float(temperature))
                text = result["choices"][0].get("text", "")
                tokens_generated = int(result.get("usage", {}).get("completion_tokens", len(text.split())))
            except Exception:
                text = "[STUB] Edge LLM runtime error — switched to stub output"
                tokens_generated = len(text.split())
                self.backend = "stub"
                self.loaded = False
        elif self.backend == "tensorrt_llm" and self._engine is not None:
            text = "[TensorRT-LLM] Inference interface ready, runtime adapter required for token decode."
            tokens_generated = min(max_tokens, len(text.split()))
        else:
            text = "[STUB] Edge LLM not loaded — install llama-cpp-python or TensorRT"
            tokens_generated = len(text.split())

        latency_ms = (time.perf_counter() - start) * 1000.0
        tps = 0.0 if latency_ms <= 1e-9 else (tokens_generated / (latency_ms / 1000.0))
        self._total_inferences += 1
        self._total_tokens += tokens_generated
        self._total_latency_ms += latency_ms
        return {
            "text": text,
            "tokens_generated": tokens_generated,
            "latency_ms": latency_ms,
            "tokens_per_second": tps,
            "backend": self.backend,
        }

    def unload(self) -> None:
        self._engine = None
        self.loaded = False
        self.backend = "stub"

    def get_stats(self) -> Dict[str, Any]:
        avg_tps = 0.0
        if self._total_latency_ms > 0:
            avg_tps = self._total_tokens / (self._total_latency_ms / 1000.0)
        return {
            "model_loaded": self.loaded,
            "backend": self.backend,
            "model_path": self.model_path,
            "memory_used_mb": self._model_memory_mb,
            "avg_tokens_per_second": avg_tps,
            "total_inferences": self._total_inferences,
        }

    def health_check(self) -> Dict[str, Any]:
        stats = self.get_stats()
        stats["max_memory_mb"] = self.max_memory_mb
        stats["memory_ok"] = self._model_memory_mb <= self.max_memory_mb
        stats["precision_hint"] = ModelPrecision.INT4.value if self._model_memory_mb > 4096 else ModelPrecision.FP16.value
        return stats
