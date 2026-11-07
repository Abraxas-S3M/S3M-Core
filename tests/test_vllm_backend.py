"""Unit tests for private vLLM strategist backend (no live network)."""

from __future__ import annotations

import json
import sys
from typing import Any
from urllib.error import URLError

import pytest

sys.path.insert(0, ".")

from src.llm_core.backends.backend_factory import BackendFactory
from src.llm_core.backends.vllm_attestation import AttestationVerifier, NullVerifier
from src.llm_core.backends.vllm_backend import (
    VllmBackend,
    VllmUrlPolicyError,
    validate_vllm_base_url,
)


class _StrictVerifier(AttestationVerifier):
    def verify(self, attestation_blob: bytes) -> bool:
        return bool(attestation_blob and attestation_blob != b"invalid")


class _FakeResponse:
    def __init__(self, status: int, body: bytes) -> None:
        self.status = status
        self._body = body

    def read(self, n: int = -1) -> bytes:
        del n
        return self._body

    def getcode(self) -> int:
        return self.status

    def __enter__(self) -> "_FakeResponse":
        return self

    def __exit__(self, *args: object) -> None:
        return None


def _make_lab_backend(
    tmp_path,
    urlopen,
    *,
    task_type: str = "strategist",
    max_output_tokens_by_task: dict[str, int] | None = None,
    request_timeout_s: float = 30.0,
    context_budget_tokens: dict[str, int] | None = None,
) -> VllmBackend:
    cortex = tmp_path / "cortex.yaml"
    cortex.write_text(
        "engine_council:\n  context_budget_tokens:\n    default: 100\n    strategist: 50\n",
        encoding="utf-8",
    )
    config: dict[str, Any] = {
        "base_url": "http://127.0.0.1:8000",
        "lab_mode": True,
        "attestation_verifier": NullVerifier(),
        "urlopen": urlopen,
        "cortex_config_path": str(cortex),
        "task_type": task_type,
        "request_timeout_s": request_timeout_s,
        "model_name": "strategist-moe",
    }
    if max_output_tokens_by_task is not None:
        config["max_output_tokens_by_task"] = max_output_tokens_by_task
    if context_budget_tokens is not None:
        config["context_budget_tokens"] = context_budget_tokens
    return VllmBackend(model_path="strategist-moe", config=config)


def test_public_hostname_is_refused() -> None:
    with pytest.raises(VllmUrlPolicyError):
        validate_vllm_base_url("https://api.openai.com/v1", frozenset())

    backend = VllmBackend(
        "strategist-moe",
        {"base_url": "https://inference.vendor.example", "lab_mode": True},
    )
    assert backend.load() is False


def test_production_without_attestation_refuses() -> None:
    calls: list[str] = []

    def urlopen(request, timeout=0, context=None):
        del timeout, context
        calls.append(request.full_url)
        if request.full_url.endswith("/v1/attestation"):
            return _FakeResponse(200, b"")
        return _FakeResponse(200, b'{"status":"ok"}')

    backend = VllmBackend(
        "strategist-moe",
        {
            "base_url": "http://127.0.0.1:9000",
            "lab_mode": False,
            "attestation_verifier": _StrictVerifier(),
            "urlopen": urlopen,
        },
    )
    assert backend.load() is False


def test_lab_with_null_verifier_works(tmp_path) -> None:
    captured: dict[str, Any] = {}

    def urlopen(request, timeout=0, context=None):
        del timeout, context
        captured["url"] = request.full_url
        if request.full_url.endswith("/health"):
            return _FakeResponse(200, b'{"status":"ok"}')
        if request.get_method() == "POST":
            body = json.loads(request.data.decode("utf-8"))
            captured["payload"] = body
            reply = {
                "choices": [{"message": {"content": "acknowledged"}}],
                "usage": {"completion_tokens": 3, "prompt_tokens": 5},
            }
            return _FakeResponse(200, json.dumps(reply).encode("utf-8"))
        return _FakeResponse(404, b"")

    backend = _make_lab_backend(tmp_path, urlopen)
    assert backend.load() is True
    assert backend.health_check()["reachable"] is True

    result = backend.generate("status", max_tokens=64)
    assert result["response"] == "acknowledged"
    assert result.get("error") is None


def test_token_cap_is_enforced(tmp_path) -> None:
    captured: dict[str, Any] = {}

    def urlopen(request, timeout=0, context=None):
        del timeout, context
        if request.full_url.endswith("/health"):
            return _FakeResponse(200, b"ok")
        if request.get_method() == "POST":
            captured["payload"] = json.loads(request.data.decode("utf-8"))
            return _FakeResponse(
                200,
                json.dumps(
                    {
                        "choices": [{"message": {"content": "ok"}}],
                        "usage": {"completion_tokens": 1, "prompt_tokens": 1},
                    }
                ).encode("utf-8"),
            )
        return _FakeResponse(404, b"")

    backend = _make_lab_backend(
        tmp_path,
        urlopen,
        max_output_tokens_by_task={"strategist": 16},
    )
    assert backend.load() is True
    backend.generate("short prompt", max_tokens=4096)
    assert captured["payload"]["max_tokens"] == 16


def test_context_budget_refuses_oversized_prompt(tmp_path) -> None:
    def urlopen(request, timeout=0, context=None):
        del timeout, context, request
        return _FakeResponse(200, b"ok")

    backend = _make_lab_backend(tmp_path, urlopen)
    assert backend.load() is True
    huge = "x" * 400
    result = backend.generate(huge, max_tokens=8)
    assert result.get("error") == "context_budget_exceeded"


def test_timeout_produces_clean_error(tmp_path) -> None:
    def urlopen(request, timeout=0, context=None):
        del timeout, context
        if request.full_url.endswith("/health"):
            return _FakeResponse(200, b"ok")
        raise TimeoutError("timed out")

    backend = _make_lab_backend(tmp_path, urlopen, request_timeout_s=0.01)
    assert backend.load() is True

    def urlopen_generate(request, timeout=0, context=None):
        del request, timeout, context
        raise URLError("timed out")

    backend._urlopen = urlopen_generate
    result = backend.generate("ping", max_tokens=4)
    assert result.get("error") == "timeout"
    assert "[ERROR]" in result["response"]


def test_factory_returns_vllm_backend() -> None:
    instance = BackendFactory.create(
        "vllm",
        "strategist-moe",
        {"base_url": "http://127.0.0.1:8000", "lab_mode": True},
    )
    assert isinstance(instance, VllmBackend)
    assert instance.backend_name == "vllm"
