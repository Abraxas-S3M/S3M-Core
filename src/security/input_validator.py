"""Input validation helpers for S3M Phase 10 security middleware."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Iterable, List, Optional, Tuple


class InputValidator:
    """Detection-first request validator for tactical API inputs."""

    ALLOWED_CLASSIFICATIONS = {
        "UNCLASSIFIED",
        "UNCLASSIFIED - FOUO",
        "CONFIDENTIAL",
        "SECRET",
        "TOP SECRET",
    }

    _PATH_TRAVERSAL_PATTERNS = (
        "../",
        "..\\",
        "%2e%2e",
        "/etc/",
        "/proc/",
        "\x00",
    )

    _INJECTION_REGEX = [
        re.compile(r"';\s*drop", re.IGNORECASE),
        re.compile(r"union\s+select", re.IGNORECASE),
        re.compile(r"\bor\s+1\s*=\s*1\b", re.IGNORECASE),
        re.compile(r"[A-Za-z0-9_]\s*--\s*$"),
        re.compile(r";\s*rm\b", re.IGNORECASE),
        re.compile(r"&&\s*cat\b", re.IGNORECASE),
        re.compile(r"\|\s*nc\b", re.IGNORECASE),
        re.compile(r"`[^`]*`"),
        re.compile(r"\$\([^)]*\)"),
        re.compile(r"\)\("),
        re.compile(r"\*\(\)"),
        re.compile(r"<script", re.IGNORECASE),
        re.compile(r"javascript:", re.IGNORECASE),
        re.compile(r"onerror\s*=", re.IGNORECASE),
        re.compile(r"onload\s*=", re.IGNORECASE),
    ]

    @staticmethod
    async def sanitize_request(request: Any) -> Tuple[bool, Optional[str]]:
        """
        Validate path/query/body for dangerous payloads.

        Returns a tuple (safe, reason). When safe is True, reason is None.
        """
        try:
            content_length = int(request.headers.get("content-length", "0"))
        except (TypeError, ValueError):
            content_length = 0
        if InputValidator.check_payload_size(content_length):
            return False, "payload exceeds allowed maximum size"

        url_path = str(getattr(getattr(request, "url", None), "path", "") or "")
        if InputValidator.check_path_traversal(url_path):
            return False, "path traversal pattern in URL path"
        if InputValidator.check_injection(url_path):
            return False, "injection pattern in URL path"

        query_params = getattr(request, "query_params", {}) or {}
        for key, value in InputValidator._iter_values(query_params):
            if InputValidator.check_path_traversal(value):
                return False, f"path traversal in query param '{key}'"
            if InputValidator.check_injection(value):
                return False, f"injection pattern in query param '{key}'"

        path_params = (getattr(request, "path_params", None) or getattr(request, "scope", {}).get("path_params", {}))
        for key, value in InputValidator._iter_values(path_params):
            if InputValidator.check_path_traversal(value):
                return False, f"path traversal in path param '{key}'"
            if InputValidator.check_injection(value):
                return False, f"injection pattern in path param '{key}'"

        body_bytes = getattr(request, "_body", None)
        if body_bytes is None and hasattr(request, "body"):
            try:
                body_bytes = await request.body()
            except Exception:
                body_bytes = None
        if isinstance(body_bytes, (bytes, bytearray)) and body_bytes:
            decoded = body_bytes.decode("utf-8", errors="ignore")
            if InputValidator.check_path_traversal(decoded):
                return False, "path traversal in request body"
            if InputValidator.check_injection(decoded):
                return False, "injection pattern in request body"

            # Deep-validate structured JSON values where possible.
            try:
                parsed = json.loads(decoded)
                for value in InputValidator._iter_nested_strings(parsed):
                    if InputValidator.check_path_traversal(value):
                        return False, "path traversal in JSON field"
                    if InputValidator.check_injection(value):
                        return False, "injection pattern in JSON field"
            except json.JSONDecodeError:
                # Non-JSON payloads are still covered by raw-string checks above.
                pass

        return True, None

    @staticmethod
    def check_path_traversal(value: str) -> bool:
        """Return True when path traversal or sensitive path probes are detected."""
        if not isinstance(value, str):
            return False
        lowered = value.lower()
        return any(pattern in lowered for pattern in InputValidator._PATH_TRAVERSAL_PATTERNS)

    @staticmethod
    def check_injection(value: str) -> bool:
        """Return True when common SQL/command/LDAP/XSS payload signatures are found."""
        if not isinstance(value, str):
            return False
        for rx in InputValidator._INJECTION_REGEX:
            if rx.search(value):
                return True
        return False

    @staticmethod
    def check_payload_size(content_length: int, max_bytes: int = 10_485_760) -> bool:
        """Return True if the payload exceeds the configured size limit."""
        try:
            return int(content_length) > int(max_bytes)
        except (TypeError, ValueError):
            return False

    @staticmethod
    def sanitize_string(value: str) -> str:
        """
        Remove null bytes/control chars while preserving tactical text content.

        The content itself is not semantically rewritten; this is for safe handling.
        """
        if not isinstance(value, str):
            return ""
        cleaned = value.replace("\x00", "")
        cleaned = "".join(
            ch for ch in cleaned if ch in ("\n", "\r", "\t") or ord(ch) >= 32
        )
        return cleaned.strip()

    @staticmethod
    def validate_file_path(path: str, allowed_prefixes: List[str] | None = None) -> Tuple[bool, str]:
        """Validate that a file path stays inside approved mission data zones."""
        if not isinstance(path, str) or not path.strip():
            return False, "path must be a non-empty string"

        candidate = InputValidator.sanitize_string(path)
        if ".." in candidate:
            return False, "path traversal is not allowed"

        allowed = allowed_prefixes or [
            "models/",
            "data/",
            "configs/",
            "/var/log/suricata/",
            "/var/ossec/",
        ]

        normalized = candidate.replace("\\", "/")
        if normalized.startswith("/"):
            normalized_abs = str(Path(normalized).resolve())
            allowed_abs = [
                str(Path(prefix).resolve()) if not prefix.startswith("/") else str(Path(prefix).resolve())
                for prefix in allowed
            ]
            if any(normalized_abs.startswith(prefix.rstrip("/") + "/") or normalized_abs == prefix.rstrip("/") for prefix in allowed_abs):
                return True, "ok"
            return False, "absolute path outside allowed prefixes"

        if any(normalized.startswith(prefix) for prefix in allowed if not prefix.startswith("/")):
            return True, "ok"
        return False, "relative path must start with an allowed prefix"

    @staticmethod
    def validate_classification(value: str) -> bool:
        """Validate NATO/GCC classification label."""
        return isinstance(value, str) and value.strip() in InputValidator.ALLOWED_CLASSIFICATIONS

    @staticmethod
    def _iter_values(values: Any) -> Iterable[Tuple[str, str]]:
        if isinstance(values, dict):
            for key, value in values.items():
                yield str(key), str(value)
            return
        if hasattr(values, "items"):
            for key, value in values.items():
                yield str(key), str(value)
            return
        return []

    @staticmethod
    def _iter_nested_strings(data: Any) -> Iterable[str]:
        if isinstance(data, str):
            yield data
        elif isinstance(data, dict):
            for key, value in data.items():
                yield str(key)
                yield from InputValidator._iter_nested_strings(value)
        elif isinstance(data, (list, tuple, set)):
            for value in data:
                yield from InputValidator._iter_nested_strings(value)
