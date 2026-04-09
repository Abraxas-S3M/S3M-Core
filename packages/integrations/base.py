"""Base adapter for all S3M integration wrappers.

Military/tactical context:
Each external open-source tool gets a thin S3M adapter that provides:
- Standardized discovery (the orchestrator can find and query it)
- Airgapped fallback (returns fixture data when offline)
- Credential validation (checks if API keys or tools are available)
- Uniform logging and error handling
"""

from __future__ import annotations

import json
import logging
import os
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List


@dataclass
class IntegrationManifest:
    name: str
    slug: str
    domain: str
    source_url: str
    license: str
    description: str
    integration_type: str  # 'adapter' | 'service' | 'dataset' | 'reference'
    capabilities: List[str] = field(default_factory=list)
    pip_dependencies: List[str] = field(default_factory=list)
    system_dependencies: List[str] = field(default_factory=list)
    docker_dependencies: List[str] = field(default_factory=list)
    airgapped_support: bool = True
    vendor_path: str = ""


class IntegrationAdapter(ABC):
    """Base class for all 495 S3M integration wrappers."""

    integration_id: str = "unknown"
    domain: str = "unknown"

    def __init__(self, mode: str | None = None):
        env_airgap = os.getenv("S3M_AIRGAPPED", "false").lower() in {"1", "true", "yes"}
        self.mode = (mode or ("airgapped" if env_airgap else "online")).lower()
        self.logger = logging.getLogger(f"s3m.integrations.{self.domain}.{self.integration_id}")
        self._fixture_dir = Path(__file__).resolve().parent / self.domain / self.integration_id / "fixtures"

    @property
    def is_airgapped(self) -> bool:
        return self.mode == "airgapped"

    def _env(self, key: str, default: str = "") -> str:
        return os.getenv(key, os.getenv(f"S3M_{key}", default))

    def _read_fixture(self, filename: str) -> Any:
        path = self._fixture_dir / filename
        if path.exists():
            return json.loads(path.read_text(encoding="utf-8"))
        return {}

    @abstractmethod
    def get_manifest(self) -> IntegrationManifest:
        raise NotImplementedError

    @abstractmethod
    def validate_availability(self) -> bool:
        """Check if the external tool is available (installed, API key set, etc.)."""
        raise NotImplementedError

    @abstractmethod
    def execute(self, params: Dict[str, Any] | None = None) -> Dict[str, Any]:
        """Run the integration's primary function."""
        raise NotImplementedError

    def health_check(self) -> Dict[str, Any]:
        available = self.validate_availability()
        return {
            "integration_id": self.integration_id,
            "domain": self.domain,
            "mode": self.mode,
            "available": available,
            "airgapped": self.is_airgapped,
        }
