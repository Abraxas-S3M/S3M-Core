"""
llama.cpp backend adapter for GGUF runtime formats.
"""

from __future__ import annotations

import time
from pathlib import Path
from typing import Dict, Optional

from src.edge_runtime.model_manifest import ManifestVariant
from src.llm_core.backends.base import BackendOutput, InferenceBackend

try:
    from llama_cpp import Llama

    LLAMA_CPP_AVAILABLE = True
except Exception:
    LLAMA_CPP_AVAILABLE = False


class LlamaCppBackend(InferenceBackend):
    backend_name = "llama_cpp"

    def __init__(self, model_id: str, variant: ManifestVariant, n_ctx: Optional[int] = None) -> None:
        super().__init__(model_id=model_id, variant_tag=variant.variant_tag, runtime_format=variant.runtime_format)
        self.variant = variant
        self.n_ctx = int(n_ctx or variant.max_context or 4096)
        self._model: Optional[object] = None

    def load(self) -> bool:
        if not LLAMA_CPP_AVAILABLE:
            self.loaded = False
            return False

        model_path = Path(self.variant.file_path)
        if not model_path.exists():
            self.loaded = False
            return False

        try:
            self._model = Llama(model_path=str(model_path), n_gpu_layers=0, n_ctx=self.n_ctx, verbose=False)
        except Exception:
            self._model = None
            self.loaded = False
            return False

        self.loaded = True
        return True

    def unload(self) -> None:
        self._model = None
        self.loaded = False

    def generate(
        self,
        prompt: str,
        max_tokens: int,
        temperature: float = 0.7,
        top_p: float = 0.9,
        stop: Optional[list] = None,
        system_prompt: Optional[str] = None,
    ) -> BackendOutput:
        if not self.loaded or self._model is None:
            return BackendOutput(
                text="[ERROR] Backend not loaded",
                tokens_generated=0,
                prompt_tokens=0,
                latency_ms=0.0,
                model_name=f"{self.model_id}:{self.variant_tag}",
                error="backend_not_loaded",
            )

        if system_prompt:
            full_prompt = f"<|system|>\n{system_prompt}\n<|user|>\n{prompt}\n<|assistant|>\n"
        else:
            full_prompt = f"<|user|>\n{prompt}\n<|assistant|>\n"

        try:
            started = time.time()
            output = self._model(
                full_prompt,
                max_tokens=int(max_tokens),
                temperature=float(temperature),
                top_p=float(top_p),
                stop=stop or ["<|end|>", "<|user|>"],
                echo=False,
            )
            latency_ms = (time.time() - started) * 1000.0
            text = str(output["choices"][0]["text"]).strip()
            usage = output.get("usage", {})
            completion_tokens = int(usage.get("completion_tokens", 0))
            prompt_tokens = int(usage.get("prompt_tokens", 0))
            return BackendOutput(
                text=text,
                tokens_generated=completion_tokens,
                prompt_tokens=prompt_tokens,
                latency_ms=latency_ms,
                model_name=f"{self.model_id}:{self.variant_tag}",
            )
        except Exception as exc:
            return BackendOutput(
                text=f"[ERROR] Inference failed: {exc}",
                tokens_generated=0,
                prompt_tokens=0,
                latency_ms=0.0,
                model_name=f"{self.model_id}:{self.variant_tag}",
                error="inference_failed",
            )

    def health_check(self) -> Dict[str, object]:
        return {
            "backend": self.backend_name,
            "runtime_format": self.runtime_format,
            "variant_tag": self.variant_tag,
            "model_file_exists": Path(self.variant.file_path).exists(),
            "loaded": self.loaded,
            "llama_cpp_available": LLAMA_CPP_AVAILABLE,
            "n_ctx": self.n_ctx,
        }
