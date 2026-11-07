"""
vLLM OpenAI-compatible backend for core-tier strategist MoE on private GPU servers.

Tactical context: the 1T-class council model runs on a classified multi-GPU rack;
S3M reaches it only over mTLS on private networks—no outbound internet inference.
"""

from __future__ import annotations

import ipaddress
import json
import logging
import re
import socket
import ssl
import time
from pathlib import Path
from typing import Any, Callable
from urllib.error import HTTPError, URLError
from urllib.parse import urljoin, urlparse
from urllib.request import Request, urlopen

from .base_backend import InferenceBackend
from .vllm_attestation import AttestationError, AttestationVerifier, NullVerifier

logger = logging.getLogger("s3m.backends.vllm")

# Rough heuristic: 4 chars ≈ 1 token for council traffic budgeting (offline, no tokenizer RPC).
_CHARS_PER_TOKEN_ESTIMATE = 4

_PRIVATE_HOST_PATTERNS = (
    re.compile(r"\.local$", re.IGNORECASE),
    re.compile(r"\.internal$", re.IGNORECASE),
    re.compile(r"\.svc$", re.IGNORECASE),
    re.compile(r"\.cluster\.local$", re.IGNORECASE),
)


class VllmUrlPolicyError(ValueError):
    """Base URL failed private-network / allowlist policy."""


def is_private_or_allowed_host(hostname: str, internal_hostnames: frozenset[str] | set[str]) -> bool:
    """
    Return True when ``hostname`` is suitable for tactically scoped inference.

    Public internet hostnames are refused unless explicitly listed in the internal allowlist
    (e.g. split-horizon DNS names that do not resolve on the public internet).
    """
    if not hostname:
        return False

    normalized = hostname.strip().lower().rstrip(".")
    if normalized in {"localhost", "127.0.0.1", "::1"}:
        return True

    if normalized in {h.strip().lower() for h in internal_hostnames}:
        return True

    for pattern in _PRIVATE_HOST_PATTERNS:
        if pattern.search(normalized):
            return True

    try:
        addr = ipaddress.ip_address(normalized)
        return addr.is_private or addr.is_loopback or addr.is_link_local
    except ValueError:
        pass

    try:
        for family in (socket.AF_INET, socket.AF_INET6):
            try:
                infos = socket.getaddrinfo(normalized, None, family, socket.SOCK_STREAM)
            except socket.gaierror:
                continue
            if not infos:
                continue
            all_private = True
            for info in infos:
                ip_str = info[4][0]
                try:
                    ip = ipaddress.ip_address(ip_str)
                except ValueError:
                    all_private = False
                    break
                if not (ip.is_private or ip.is_loopback or ip.is_link_local):
                    all_private = False
                    break
            if all_private and infos:
                return True
    except OSError:
        logger.debug("DNS resolution failed for host policy check: %s", normalized, exc_info=True)

    return False


def validate_vllm_base_url(base_url: str, internal_hostnames: frozenset[str] | set[str] | None = None) -> str:
    """Normalize and validate the OpenAI-compatible base URL."""
    if not base_url or not str(base_url).strip():
        raise VllmUrlPolicyError("base_url must be configured")

    parsed = urlparse(str(base_url).strip())
    if parsed.scheme not in {"http", "https"}:
        raise VllmUrlPolicyError(f"unsupported URL scheme: {parsed.scheme!r}")

    host = parsed.hostname
    if host is None:
        raise VllmUrlPolicyError("base_url missing hostname")

    allowlist = internal_hostnames or frozenset()
    if not is_private_or_allowed_host(host, allowlist):
        raise VllmUrlPolicyError(
            f"refusing public or non-allowlisted inference host: {host!r}"
        )

    normalized = f"{parsed.scheme}://{parsed.netloc}".rstrip("/")
    return normalized


def estimate_prompt_tokens(prompt: str) -> int:
    """Offline token estimate for context budgeting without calling the server tokenizer."""
    text = prompt or ""
    return max(1, (len(text) + _CHARS_PER_TOKEN_ESTIMATE - 1) // _CHARS_PER_TOKEN_ESTIMATE)


def load_context_budget_from_yaml(path: str | Path) -> dict[str, int]:
    """Load ``engine_council.context_budget_tokens`` from ``configs/cortex.yaml``."""
    config_path = Path(path)
    if not config_path.is_file():
        return {}

    try:
        import yaml
    except ImportError:
        logger.warning("PyYAML unavailable; context budgets not loaded from %s", config_path)
        return {}

    with config_path.open(encoding="utf-8") as handle:
        raw = yaml.safe_load(handle) or {}

    council = raw.get("engine_council") or {}
    budgets = council.get("context_budget_tokens") or {}
    return {str(k): int(v) for k, v in budgets.items()}


class VllmBackend(InferenceBackend):
    """HTTP client for a private vLLM OpenAI-compatible chat/completions endpoint."""

    def __init__(self, model_path: str, config: dict[str, Any]) -> None:
        super().__init__(model_path=model_path, config=config)
        self.base_url = str(config.get("base_url", "")).strip()
        self._internal_hostnames: set[str] = set(config.get("internal_hostnames") or [])
        self._request_timeout_s = float(config.get("request_timeout_s", 120.0))
        self._health_path = str(config.get("health_path", "/health"))
        self._attestation_path = str(config.get("attestation_path", "/v1/attestation"))
        self._chat_path = str(config.get("chat_completions_path", "/v1/chat/completions"))
        self._lab_mode = bool(config.get("lab_mode", False))
        self._model_name = str(config.get("model_name") or self.model_path or "strategist")
        self._task_type = str(config.get("task_type", "strategist"))
        self._stream = bool(config.get("stream", False))

        self._max_tokens_by_task: dict[str, int] = {
            str(k): int(v) for k, v in (config.get("max_output_tokens_by_task") or {}).items()
        }
        default_cap = int(config.get("max_output_tokens_default", 4096))
        self._default_max_output = default_cap

        cortex_path = config.get("cortex_config_path", "configs/cortex.yaml")
        file_budgets = load_context_budget_from_yaml(cortex_path)
        merged_budgets = dict(file_budgets)
        merged_budgets.update(config.get("context_budget_tokens") or {})
        self._context_budget_tokens = merged_budgets

        verifier = config.get("attestation_verifier")
        if verifier is None:
            verifier = NullVerifier() if self._lab_mode else None
        self._attestation_verifier: AttestationVerifier | None = verifier
        self._attestation_verified = False
        self._vault_client = config.get("vault_client")
        self._vault_mtls_paths: dict[str, str] = dict(config.get("vault_mtls_paths") or {})
        self._mtls_session_id = str(config.get("mtls_session_id", "vllm-strategist"))
        self._ssl_context: ssl.SSLContext | None = None
        self._urlopen: Callable[..., Any] = config.get("urlopen", urlopen)

    @property
    def backend_name(self) -> str:
        return "vllm"

    def load(self) -> bool:
        try:
            self.base_url = validate_vllm_base_url(self.base_url, self._internal_hostnames)
        except VllmUrlPolicyError:
            logger.exception("vLLM base URL rejected by network policy")
            self._loaded = False
            return False

        try:
            self._ssl_context = self._build_ssl_context()
        except (OSError, ValueError, RuntimeError):
            logger.exception("Failed to build mTLS SSL context from vault material")
            self._loaded = False
            return False

        if not self._lab_mode:
            if self._attestation_verifier is None or isinstance(self._attestation_verifier, NullVerifier):
                logger.error("Production vLLM load requires a non-Null attestation verifier")
                self._loaded = False
                return False
            if not self._ensure_attestation():
                self._loaded = False
                return False
        else:
            if self._attestation_verifier is not None and not self._attestation_verified:
                # Lab may skip remote attestation fetch when verifier is Null and blob provided in config.
                config_blob = self.config.get("lab_attestation_blob")
                blob = config_blob if config_blob is not None else b"lab-placeholder"
                if isinstance(blob, str):
                    blob = blob.encode("utf-8")
                if not self._attestation_verifier.verify(blob):
                    self._loaded = False
                    return False
                self._attestation_verified = True

        health = self.health_check()
        if not health.get("reachable"):
            self._loaded = False
            return False

        self._loaded = True
        return True

    def unload(self) -> None:
        self._loaded = False
        self._attestation_verified = False
        self._ssl_context = None

    def generate(
        self,
        prompt: str,
        max_tokens: int = 512,
        temperature: float = 0.7,
        top_p: float = 0.9,
        stop: list[str] | None = None,
    ) -> dict[str, Any]:
        if not self._loaded:
            return self._error_result("Model not loaded")

        budget = self._resolve_context_budget()
        prompt_tokens_est = estimate_prompt_tokens(prompt)
        if prompt_tokens_est > budget:
            return self._error_result(
                f"prompt exceeds context budget ({prompt_tokens_est} > {budget} tokens)",
                error_code="context_budget_exceeded",
            )

        task_cap = self._max_tokens_by_task.get(self._task_type, self._default_max_output)
        effective_max = min(int(max_tokens), task_cap)
        if effective_max <= 0:
            return self._error_result("max_tokens capped to zero by task policy", error_code="token_cap")

        url = urljoin(self.base_url + "/", self._chat_path.lstrip("/"))
        payload: dict[str, Any] = {
            "model": self._model_name,
            "messages": [{"role": "user", "content": prompt}],
            "max_tokens": effective_max,
            "temperature": float(temperature),
            "top_p": float(top_p),
            "stream": self._stream,
        }
        if stop:
            payload["stop"] = stop

        body = json.dumps(payload).encode("utf-8")
        request = Request(
            url,
            data=body,
            headers={"Content-Type": "application/json", "Accept": "application/json"},
            method="POST",
        )

        started = time.perf_counter()
        try:
            with self._urlopen(
                request,
                timeout=self._request_timeout_s,
                context=self._ssl_context,
            ) as response:
                raw = response.read()
            latency_ms = (time.perf_counter() - started) * 1000.0

            if self._stream:
                text, completion_tokens = self._parse_sse_completions(raw)
            else:
                parsed = json.loads(raw.decode("utf-8"))
                text, completion_tokens, usage_prompt = self._parse_chat_completion(parsed)
                if usage_prompt:
                    prompt_tokens_est = int(usage_prompt)

            tokens_per_second = (
                (completion_tokens / (latency_ms / 1000.0)) if latency_ms > 0 and completion_tokens else 0.0
            )
            return {
                "response": text,
                "tokens_generated": completion_tokens,
                "prompt_tokens": prompt_tokens_est,
                "latency_ms": latency_ms,
                "tokens_per_second": tokens_per_second,
                "max_tokens_applied": effective_max,
            }
        except TimeoutError:
            return self._error_result(
                f"inference request timed out after {self._request_timeout_s}s",
                error_code="timeout",
            )
        except HTTPError as exc:
            logger.warning("vLLM HTTP error: %s", exc)
            return self._error_result(f"HTTP {exc.code}: {exc.reason}", error_code="http_error")
        except (URLError, OSError, json.JSONDecodeError) as exc:
            if "timed out" in str(exc).lower():
                return self._error_result(
                    f"inference request timed out after {self._request_timeout_s}s",
                    error_code="timeout",
                )
            logger.exception("vLLM generation failed")
            return self._error_result(str(exc), error_code="inference_failed")

    def health_check(self) -> dict[str, Any]:
        url = urljoin(self.base_url + "/", self._health_path.lstrip("/"))
        request = Request(url, method="GET")
        reachable = False
        status_code: int | None = None
        detail = ""

        try:
            with self._urlopen(request, timeout=min(self._request_timeout_s, 30.0), context=self._ssl_context) as resp:
                status_code = getattr(resp, "status", None) or resp.getcode()
                detail = resp.read(256).decode("utf-8", errors="replace")
                reachable = 200 <= int(status_code) < 300
        except (HTTPError, URLError, OSError, TimeoutError) as exc:
            detail = str(exc)

        return {
            "backend": self.backend_name,
            "loaded": self._loaded,
            "base_url": self.base_url,
            "reachable": reachable,
            "status_code": status_code,
            "attestation_verified": self._attestation_verified,
            "lab_mode": self._lab_mode,
            "detail": detail[:200],
        }

    def _resolve_context_budget(self) -> int:
        return int(
            self._context_budget_tokens.get(
                self._task_type,
                self._context_budget_tokens.get("default", 32768),
            )
        )

    def _ensure_attestation(self) -> bool:
        if self._attestation_verified:
            return True

        url = urljoin(self.base_url + "/", self._attestation_path.lstrip("/"))
        request = Request(url, method="GET")
        try:
            with self._urlopen(request, timeout=self._request_timeout_s, context=self._ssl_context) as resp:
                blob = resp.read()
        except (HTTPError, URLError, OSError, TimeoutError) as exc:
            logger.error("Failed to fetch attestation document: %s", exc)
            return False

        if not blob:
            logger.error("Empty attestation document from server")
            return False

        if self._attestation_verifier is None or not self._attestation_verifier.verify(blob):
            raise AttestationError("attestation verification failed")

        self._attestation_verified = True
        return True

    def _build_ssl_context(self) -> ssl.SSLContext | None:
        cert_path, key_path, ca_path = self._resolve_mtls_paths()
        if not cert_path and not key_path and not ca_path:
            if self.base_url.startswith("https://"):
                logger.warning("HTTPS vLLM endpoint without mTLS material; refusing in production")
                if not self._lab_mode:
                    raise ValueError("mTLS client certificate required for HTTPS vLLM in production")
            return None

        if not (cert_path and key_path):
            raise ValueError("vault must provide both client certificate and private key paths")

        ctx = ssl.create_default_context(cafile=ca_path if ca_path and Path(ca_path).is_file() else None)
        ctx.load_cert_chain(certfile=cert_path, keyfile=key_path)
        ctx.check_hostname = True
        ctx.verify_mode = ssl.CERT_REQUIRED
        return ctx

    def _resolve_mtls_paths(self) -> tuple[str | None, str | None, str | None]:
        direct_cert = self.config.get("mtls_client_cert_path")
        direct_key = self.config.get("mtls_client_key_path")
        direct_ca = self.config.get("mtls_ca_cert_path")
        if direct_cert and direct_key:
            return str(direct_cert), str(direct_key), str(direct_ca) if direct_ca else None

        if not self._vault_client or not self._vault_mtls_paths:
            return None, None, None

        session = self._mtls_session_id
        cert = self._read_vault_path(self._vault_mtls_paths.get("client_cert", ""), session)
        key = self._read_vault_path(self._vault_mtls_paths.get("client_key", ""), session)
        ca = self._read_vault_path(self._vault_mtls_paths.get("ca_cert", ""), session)
        return cert, key, ca

    def _read_vault_path(self, vault_path: str, session_id: str) -> str | None:
        if not vault_path:
            return None
        value = self._vault_client.get_secret(vault_path, session_id)
        path = Path(value.strip())
        if path.is_file():
            return str(path)
        raise ValueError(f"vault secret is not a readable file path: {vault_path}")

    @staticmethod
    def _parse_chat_completion(parsed: dict[str, Any]) -> tuple[str, int, int | None]:
        choices = parsed.get("choices") or []
        text = ""
        if choices:
            message = choices[0].get("message") or {}
            text = str(message.get("content") or choices[0].get("text") or "")
        usage = parsed.get("usage") or {}
        completion_tokens = int(usage.get("completion_tokens", 0))
        if not completion_tokens and text:
            completion_tokens = max(1, len(text) // _CHARS_PER_TOKEN_ESTIMATE)
        prompt_tokens = usage.get("prompt_tokens")
        return text, completion_tokens, int(prompt_tokens) if prompt_tokens is not None else None

    @staticmethod
    def _parse_sse_completions(raw: bytes) -> tuple[str, int]:
        chunks: list[str] = []
        count = 0
        for line in raw.decode("utf-8", errors="replace").splitlines():
            line = line.strip()
            if not line.startswith("data:"):
                continue
            data = line[5:].strip()
            if data == "[DONE]":
                break
            try:
                event = json.loads(data)
            except json.JSONDecodeError:
                continue
            choices = event.get("choices") or []
            if not choices:
                continue
            delta = choices[0].get("delta") or {}
            piece = delta.get("content")
            if piece:
                chunks.append(str(piece))
                count += 1
        text = "".join(chunks)
        if not count and text:
            count = max(1, len(text) // _CHARS_PER_TOKEN_ESTIMATE)
        return text, count

    @staticmethod
    def _error_result(message: str, error_code: str = "error") -> dict[str, Any]:
        return {
            "response": f"[ERROR] {message}",
            "tokens_generated": 0,
            "prompt_tokens": 0,
            "latency_ms": 0.0,
            "tokens_per_second": 0.0,
            "error": error_code,
        }
