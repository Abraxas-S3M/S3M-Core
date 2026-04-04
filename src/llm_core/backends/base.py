"""
Backend abstraction for local inference runtimes.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Dict, Optional


@dataclass
class BackendOutput:
    text: str
    tokens_generated: int
    prompt_tokens: int
    latency_ms: float
    model_name: str
    error: Optional[str] = None


class InferenceBackend(ABC):
    """Common runtime interface used by InferenceEngine."""

    backend_name: str = "unknown"

    def __init__(self, model_id: str, variant_tag: str, runtime_format: str) -> None:
        self.model_id = str(model_id)
        self.variant_tag = str(variant_tag)
        self.runtime_format = str(runtime_format)
        self.loaded = False

    @abstractmethod
    def load(self) -> bool:
        raise NotImplementedError

    @abstractmethod
    def unload(self) -> None:
        raise NotImplementedError

    @abstractmethod
    def generate(
        self,
        prompt: str,
        max_tokens: int,
        temperature: float = 0.7,
        top_p: float = 0.9,
        stop: Optional[list] = None,
        system_prompt: Optional[str] = None,
    ) -> BackendOutput:
        raise NotImplementedError

    @abstractmethod
    def health_check(self) -> Dict[str, object]:
        raise NotImplementedError
