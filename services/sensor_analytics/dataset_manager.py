"""Remote sensing dataset registry manager for Layer 09."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
import os
from typing import Any, Dict, List

import yaml


@dataclass
class RemoteSensingDatasetManager:
    registry_path: str = "configs/sensor-analytics/datasets.yaml"
    datasets: List[Dict[str, Any]] = field(default_factory=list)

    def __post_init__(self) -> None:
        self._load_registry()

    def _load_registry(self) -> None:
        if not os.path.exists(self.registry_path):
            self.datasets = []
            return
        with open(self.registry_path, "r", encoding="utf-8") as handle:
            payload = yaml.safe_load(handle) or {}
        items = payload.get("datasets", [])
        self.datasets = items if isinstance(items, list) else []

    def list_datasets(self) -> List[Dict[str, Any]]:
        return list(self.datasets)

    def health_check(self) -> Dict[str, Any]:
        return {
            "registry_path": self.registry_path,
            "datasets_count": len(self.datasets),
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

