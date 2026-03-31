"""Shared normalization helpers for Layer 06 dashboard providers."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Mapping, Tuple


def utc_now_iso() -> str:
    """Return UTC timestamp string for tactical audit/events."""
    return datetime.now(timezone.utc).isoformat()


def now_iso() -> str:
    """Alias used by threat provider for consistency."""
    return utc_now_iso()


def normalize_status(value: Any) -> str:
    val = str(value or "degraded").lower()
    if val in {"operational", "degraded", "critical", "unavailable"}:
        return val
    return "degraded"


def clamp(value: Any, minimum: float, maximum: float, default: float = 0.0) -> float:
    """Clamp numeric values to secure bounds with safe fallback."""
    try:
        numeric = float(value)
    except Exception:
        numeric = float(default)
    return max(minimum, min(maximum, numeric))


def coerce_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except Exception:
        return int(default)


def clamp_int(value: Any, minimum: int, maximum: int, default: int) -> int:
    numeric = coerce_int(value, default)
    return max(minimum, min(maximum, numeric))


def coerce_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except Exception:
        return float(default)


def normalize_position(value: Any) -> Tuple[float, float, float]:
    """Normalize tuple/list/dict positions for map rendering."""
    if isinstance(value, Mapping):
        return (
            coerce_float(value.get("x"), 0.0),
            coerce_float(value.get("y"), 0.0),
            coerce_float(value.get("z"), 0.0),
        )
    if isinstance(value, (tuple, list)):
        if len(value) == 2:
            return coerce_float(value[0], 0.0), coerce_float(value[1], 0.0), 0.0
        if len(value) >= 3:
            return coerce_float(value[0], 0.0), coerce_float(value[1], 0.0), coerce_float(value[2], 0.0)
    return 0.0, 0.0, 0.0


def coerce_position(value: Any) -> Tuple[float, float, float]:
    return normalize_position(value)


def normalize_position_dict(value: Any) -> Dict[str, float]:
    x, y, z = normalize_position(value)
    return {"x": x, "y": y, "z": z}


def as_dict(value: Any) -> Dict[str, Any]:
    """Serialize dataclass/object/dict into plain dictionary safely."""
    if isinstance(value, dict):
        return dict(value)
    if hasattr(value, "to_dict") and callable(getattr(value, "to_dict")):
        try:
            data = value.to_dict()
            if isinstance(data, dict):
                return dict(data)
        except Exception:
            pass
    if hasattr(value, "__dict__"):
        try:
            return dict(vars(value))
        except Exception:
            return {}
    return {}


def to_dict(value: Any) -> Dict[str, Any]:
    return as_dict(value)


def parse_iso_time(value: Any) -> datetime | None:
    if isinstance(value, datetime):
        return value if value.tzinfo is not None else value.replace(tzinfo=timezone.utc)
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        parsed = datetime.fromisoformat(value)
    except Exception:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed


def parse_iso_datetime(value: Any) -> datetime | None:
    return parse_iso_time(value)

