"""Secret scrubbing for Cortex traces and case reports.

Military/tactical context: audit and explainability exports leave the classified
enclave; credential patterns must be stripped before forensic bundles ship.
"""

from __future__ import annotations

import re
from typing import Any

from s3m_core.defense.filesystem.credential_scrubber import CredentialScrubber

_SCRUBBER_SINGLETON = CredentialScrubber(scan_paths=["/"])


def scrub_text(value: str) -> str:
    """Redact token-like content from a string using defense credential patterns."""
    redacted = str(value or "")
    for pattern in _SCRUBBER_SINGLETON._PATTERNS.values():
        redacted, _ = pattern.subn("[REDACTED]", redacted)
    return redacted


def scrub_mapping(payload: Any) -> Any:
    """Recursively scrub strings inside JSON-serializable structures."""
    if isinstance(payload, str):
        return scrub_text(payload)
    if isinstance(payload, dict):
        return {str(key): scrub_mapping(val) for key, val in payload.items()}
    if isinstance(payload, list):
        return [scrub_mapping(item) for item in payload]
    if isinstance(payload, tuple):
        return tuple(scrub_mapping(item) for item in payload)
    return payload


_TOKEN_LIKE = re.compile(
    r"(?i)(?:bearer\s+[A-Za-z0-9_\-\.=]{20,}|"
    r"sk-[A-Za-z0-9]{20,}|"
    r"eyJ[A-Za-z0-9_\-]{10,}\.[A-Za-z0-9_\-]{10,}\.[A-Za-z0-9_\-]{10,})"
)


def contains_token_like_strings(text: str) -> bool:
    """Return True when output still resembles a secret (used in tests)."""
    return bool(_TOKEN_LIKE.search(str(text or "")))
