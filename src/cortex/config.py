"""Load offline Cortex configuration from ``configs/cortex.yaml``."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Any, Dict

import yaml

_REPO_ROOT = Path(__file__).resolve().parents[2]
_DEFAULT_CONFIG = _REPO_ROOT / "configs" / "cortex.yaml"


@lru_cache(maxsize=1)
def load_cortex_config(path: str | None = None) -> Dict[str, Any]:
    config_path = Path(path) if path else _DEFAULT_CONFIG
    if not config_path.is_file():
        return {
            "mission": {"weights": {1: 1.0, 2: 1.5, 3: 2.0, 4: 3.0, 5: 5.0}},
            "default_disruption_cost": 1.0,
            "event_track": "cyber_cortex",
        }
    raw = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
    weights = raw.get("mission", {}).get("weights", {})
    normalized = {int(k): float(v) for k, v in weights.items()}
    raw.setdefault("mission", {})["weights"] = normalized
    return raw


def mission_weight(priority: int, config: Dict[str, Any] | None = None) -> float:
    """Map mission priority (1–5) to MRC cost multiplier."""
    cfg = config or load_cortex_config()
    weights: Dict[int, float] = cfg.get("mission", {}).get("weights", {})
    return float(weights.get(int(priority), 1.0))
