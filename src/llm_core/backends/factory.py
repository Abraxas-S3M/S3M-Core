"""
Backend factory that maps manifest runtime formats to implementations.
"""

from __future__ import annotations

from src.edge_runtime.model_manifest import ManifestVariant
from src.llm_core.backends.base import InferenceBackend
from src.llm_core.backends.llama_cpp_backend import LlamaCppBackend


class BackendFactory:
    @staticmethod
    def create(model_id: str, variant: ManifestVariant) -> InferenceBackend:
        runtime = str(variant.runtime_format).strip().lower()
        if runtime in {"gguf", "llama.cpp", "llama_cpp"}:
            return LlamaCppBackend(model_id=model_id, variant=variant, n_ctx=variant.max_context)
        raise ValueError(f"Unsupported runtime_format '{variant.runtime_format}' for model '{model_id}'")
