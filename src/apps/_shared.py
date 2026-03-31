"""Shared helpers for Phase 11 domain apps."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Iterable, List, Sequence


def utc_now_iso() -> str:
    """Return UTC timestamp in ISO-8601 format."""
    return datetime.now(timezone.utc).isoformat()


def ensure_non_empty_text(value: Any, field_name: str) -> str:
    """Validate string-like input and normalize whitespace."""
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name} must be a non-empty string")
    return value.strip()


def as_list(value: Any) -> List[Any]:
    """Normalize optional list-like values."""
    if value is None:
        return []
    if isinstance(value, list):
        return value
    return [value]


def first_non_empty(*candidates: Any, default: str = "") -> str:
    """Return first non-empty string from candidates."""
    for candidate in candidates:
        if isinstance(candidate, str) and candidate.strip():
            return candidate.strip()
    return default


def safe_float(value: Any, default: float = 0.0) -> float:
    """Coerce numeric value to float with fallback."""
    try:
        return float(value)
    except (TypeError, ValueError):
        return float(default)


def safe_int(value: Any, default: int = 0) -> int:
    """Coerce numeric value to int with fallback."""
    try:
        return int(value)
    except (TypeError, ValueError):
        return int(default)


def clamp(value: float, low: float, high: float) -> float:
    """Clamp numeric values into inclusive range."""
    return max(low, min(high, value))


def join_lines(lines: Sequence[str]) -> str:
    """Join text lines ignoring empty entries."""
    return "\n".join(line for line in lines if isinstance(line, str) and line.strip())


def normalize_coords(value: Any, dims: int = 3, default: tuple[float, ...] | None = None) -> tuple[float, ...]:
    """Normalize coordinate tuples for tactical geometry operations."""
    if default is None:
        default = tuple(0.0 for _ in range(dims))
    if isinstance(value, (list, tuple)) and len(value) >= dims:
        out = []
        for idx in range(dims):
            out.append(safe_float(value[idx], default[idx]))
        return tuple(out)
    return default


def contains_arabic(text: str) -> bool:
    """Detect Arabic script characters for routing decisions."""
    if not isinstance(text, str):
        return False
    return any("\u0600" <= ch <= "\u06FF" for ch in text)


def summarize_counts(items: Iterable[dict], field: str) -> dict[str, int]:
    """Count occurrences by dictionary field."""
    counts: dict[str, int] = {}
    for item in items:
        key = str(item.get(field, "unknown"))
        counts[key] = counts.get(key, 0) + 1
    return counts
