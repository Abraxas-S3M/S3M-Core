"""
S3M Backend Base Interface
Defines a pluggable inference contract for air-gapped tactical edge deployment.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any
import logging

logger = logging.getLogger("s3m.backends.base")


class InferenceBackend(ABC):
    """Abstract runtime backend used by S3M inference services."""

    def __init__(self, model_path: str, config: dict[str, Any]) -> None:
        self.model_path = model_path
        self.config = config
        self._loaded = False

    @property
    @abstractmethod
    def backend_name(self) -> str:
        """Human-readable backend identifier."""

    @property
    def is_loaded(self) -> bool:
        """Return True when the backend has loaded model resources."""
        return self._loaded

    @abstractmethod
    def load(self) -> bool:
        """Load model artifacts into runtime memory."""

    @abstractmethod
    def unload(self) -> None:
        """Release model resources and runtime handles."""

    @abstractmethod
    def generate(
        self,
        prompt: str,
        max_tokens: int = 512,
        temperature: float = 0.7,
        top_p: float = 0.9,
        stop: list[str] | None = None,
    ) -> dict[str, Any]:
        """
        Run generation and return normalized telemetry payload.

        Expected keys: response, tokens_generated, prompt_tokens, latency_ms, tokens_per_second.
        """

    @abstractmethod
    def health_check(self) -> dict[str, Any]:
        """Return backend availability and runtime health details."""

    def estimate_memory_mb(self) -> float:
        """Estimate model footprint in memory from model file size."""
        try:
            model_size_bytes = Path(self.model_path).stat().st_size
        except OSError:
            logger.debug("Unable to read model file for memory estimate: %s", self.model_path)
            return 0.0
        return model_size_bytes / (1024 * 1024)
