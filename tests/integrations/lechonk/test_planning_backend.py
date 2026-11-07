"""Le Chonk planning vLLM adapter tests (no live network)."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from src.integrations.lechonk.circuit_breaker import CircuitBreaker
from src.integrations.lechonk.planning_backend import LeChonkPlanningBackend
from src.llm_core.backends.vllm_backend import VllmBackend


def _backend() -> VllmBackend:
    return VllmBackend(
        model_path="mistral-large-4",
        config={
            "base_url": "http://127.0.0.1:8000",
            "lab_mode": True,
            "internal_hostnames": frozenset(),
            "max_tokens": 128,
        },
    )


def test_circuit_open_blocks_generate() -> None:
    backend = _backend()
    backend._loaded = True  # noqa: SLF001 — test stub
    adapter = LeChonkPlanningBackend(backend, circuit_breaker=CircuitBreaker(failure_threshold=1))
    adapter._breaker.record_failure()
    adapter._breaker.record_failure()
    adapter._breaker.record_failure()
    out = adapter.generate_planning("plan ingress")
    assert out["success"] is False
    assert out["error"] == "circuit_open"


def test_generate_reports_provenance_without_fabricating_verification() -> None:
    backend = _backend()
    backend._loaded = True  # noqa: SLF001
    backend.generate = MagicMock(return_value={"success": True, "text": "COA alpha"})  # type: ignore[method-assign]
    adapter = LeChonkPlanningBackend(backend)
    out = adapter.generate_planning("suggest COA")
    assert out["success"] is True
    assert out["provenance"]["human_review_required"] is True
    assert out["provenance"]["inference_verified"] is False
