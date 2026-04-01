"""Base adapter contract used by GEOINT provider modules."""

from __future__ import annotations

import json
import os
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass(slots=True)
class ProviderManifest:
    provider_id: str
    category: str
    tier: str
    auth_type: str
    rate_limit_rpm: int
    required_env_vars: list[str] = field(default_factory=list)
    optional_env_vars: list[str] = field(default_factory=list)
    description: str = ""


class ProviderAdapter(ABC):
    provider_id = "unknown"

    def __init__(self, mode: str | None = None):
        env_airgap = os.getenv("S3M_AIRGAPPED", "false").lower() in {"1", "true", "yes"}
        self.mode = (mode or ("airgapped" if env_airgap else "online")).lower()

    @property
    def is_airgapped(self) -> bool:
        return self.mode == "airgapped"

    def _env(self, key: str, default: str = "") -> str:
        return os.getenv(key, os.getenv(f"S3M_{key}", default))

    def _read_json(self, path: str | Path) -> dict[str, Any]:
        return json.loads(Path(path).read_text(encoding="utf-8"))

    def _read_text(self, path: str | Path) -> str:
        return Path(path).read_text(encoding="utf-8")

    @abstractmethod
    def get_manifest(self) -> ProviderManifest:
        raise NotImplementedError

    @abstractmethod
    def validate_credentials(self) -> bool:
        raise NotImplementedError

    @abstractmethod
    def fetch(self, params: dict[str, Any]) -> Any:
        raise NotImplementedError

    @abstractmethod
    def normalize(self, raw_data: Any) -> Any:
        raise NotImplementedError

    @abstractmethod
    def health_check(self) -> dict[str, Any]:
        raise NotImplementedError

    def fetch_and_normalize(self, params: dict[str, Any] | None = None) -> Any:
        return self.normalize(self.fetch(params or {}))
