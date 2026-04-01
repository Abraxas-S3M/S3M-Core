"""Utility helpers for GEOINT provider adapters and pipeline."""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def parse_datetime(value: str | None) -> datetime:
    if not value:
        return utc_now()
    normalized = value.replace("Z", "+00:00")
    try:
        return datetime.fromisoformat(normalized)
    except ValueError:
        for fmt in ("%Y-%m-%d", "%Y-%m-%d %H:%M:%S"):
            try:
                return datetime.strptime(value, fmt).replace(tzinfo=timezone.utc)
            except ValueError:
                continue
    return utc_now()


def ensure_directory(path: str | Path) -> Path:
    target = Path(path)
    target.mkdir(parents=True, exist_ok=True)
    return target


def _as_plain_dict(observation: Any) -> dict[str, Any]:
    if hasattr(observation, "to_dict"):
        return observation.to_dict()
    if isinstance(observation, dict):
        return observation
    return json.loads(json.dumps(observation, default=str))


def compute_observation_hash(observation: Any) -> str:
    record = _as_plain_dict(observation)
    geo = record.get("geo_point", {})
    components = [
        str(record.get("observation_type", "")),
        str(record.get("satellite", "")),
        str(record.get("timestamp", "")),
        f"{geo.get('lat', ''):.5f}" if isinstance(geo.get("lat"), (int, float)) else str(geo.get("lat", "")),
        f"{geo.get('lon', ''):.5f}" if isinstance(geo.get("lon"), (int, float)) else str(geo.get("lon", "")),
        str(record.get("collection", "")),
    ]
    return hashlib.sha256("|".join(components).encode("utf-8")).hexdigest()
