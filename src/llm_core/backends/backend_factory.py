"""
S3M Backend Factory
Creates runtime-specific backend instances for tactical offline inference pipelines.
"""

from __future__ import annotations

from typing import Any
import logging

from .base_backend import InferenceBackend
from .llama_cpp_backend import LlamaCppBackend
from .onnx_backend import OnnxBackend
from .openvino_backend import OpenVinoBackend

logger = logging.getLogger("s3m.backends.factory")


class BackendFactory:
    """Factory for selecting the appropriate backend implementation."""

    @staticmethod
    def create(runtime_format: str, model_path: str, config: dict[str, Any]) -> InferenceBackend:
        """
        runtime_format: one of "gguf", "onnx", "openvino"
        Returns the appropriate backend instance.
        Raises ValueError for unknown format.
        """
        normalized = runtime_format.strip().lower()

        if normalized in {"gguf", "llama_cpp", "llama.cpp"}:
            return LlamaCppBackend(model_path=model_path, config=config)
        if normalized == "onnx":
            return OnnxBackend(model_path=model_path, config=config)
        if normalized == "openvino":
            return OpenVinoBackend(model_path=model_path, config=config)

        logger.error("Unknown runtime format requested: %s", runtime_format)
        raise ValueError(f"Unknown runtime format: {runtime_format}")
