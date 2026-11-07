"""Load Layer 07 cyber operations configuration for offline edge nodes."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Any, Dict

import yaml

_DEFAULT_CYBER_CONFIG = Path("configs/cyber.yaml")


@lru_cache(maxsize=4)
def load_cyber_config(config_path: str = str(_DEFAULT_CYBER_CONFIG)) -> Dict[str, Any]:
    path = Path(config_path)
    if not path.is_file():
        return {}
    payload = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    if not isinstance(payload, dict):
        return {}
    return payload


def soar_settings(config_path: str = str(_DEFAULT_CYBER_CONFIG)) -> Dict[str, Any]:
    """Return SOAR subsection from cyber.yaml."""
    config = load_cyber_config(config_path)
    soar = config.get("soar", {})
    return dict(soar) if isinstance(soar, dict) else {}


def soar_auto_execute(config_path: str = str(_DEFAULT_CYBER_CONFIG)) -> bool:
    """Whether SOAR may auto-run mutate steps after PolicyGate approval."""
    return bool(soar_settings(config_path).get("auto_execute", False))
