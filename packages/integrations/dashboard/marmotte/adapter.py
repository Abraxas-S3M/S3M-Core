"""Dashboard integration wrapper for Marmotte.

Military/tactical context:
This adapter standardizes telemetry exchange so mission operators can query
Marmotte workflows through a uniform S3M interface in contested, airgapped
deployments where direct internet access is prohibited.
"""

from __future__ import annotations

import logging
import shutil
from pathlib import Path
from typing import Any

import yaml

from packages.integrations.base import IntegrationAdapter, IntegrationManifest


class MarmotteAdapter(IntegrationAdapter):
    """Adapter for tactical dashboard ingestion and status checks."""

    integration_id = "marmotte"
    domain = "dashboard"

    _repo_env_var = "MARMOTTE_PATH"
    _fallback_binary = "docker"

    def __init__(self, mode: str | None = None) -> None:
        super().__init__(mode=mode)
        self.logger = logging.getLogger(f"s3m.integrations.dashboard.{self.integration_id}")

    @staticmethod
    def _coerce_list(value: Any) -> list[str]:
        if value is None:
            return []
        if isinstance(value, list):
            return [str(item) for item in value]
        return [str(value)]

    def _manifest_path(self) -> Path:
        return Path(__file__).resolve().parent / "manifest.yaml"

    def get_manifest(self) -> IntegrationManifest:
        raw = yaml.safe_load(self._manifest_path().read_text(encoding="utf-8")) or {}
        return IntegrationManifest(
            name=str(raw.get("name") or self.integration_id),
            slug=str(raw.get("slug") or self.integration_id),
            domain=str(raw.get("domain") or self.domain),
            source_url=str(raw.get("source_url") or ""),
            license=str(raw.get("license") or "unknown"),
            description=str(raw.get("description") or "IT asset management dashboard wrapper adaptable for military base infrastructure and sustainment visibility."),
            integration_type=str(raw.get("integration_type") or "adapter"),
            capabilities=self._coerce_list(raw.get("capabilities")),
            pip_dependencies=self._coerce_list(raw.get("pip_dependencies")),
            system_dependencies=self._coerce_list(raw.get("system_dependencies")),
            docker_dependencies=self._coerce_list(raw.get("docker_dependencies")),
            airgapped_support=bool(raw.get("airgapped_support", True)),
            vendor_path=str(raw.get("vendor_path") or ""),
        )

    def validate_availability(self) -> bool:
        if self.is_airgapped:
            fixture_payload = self._read_fixture("sample_response.json")
            return isinstance(fixture_payload, dict) and bool(fixture_payload)

        local_repo_path = self._env(self._repo_env_var)
        if local_repo_path:
            return Path(local_repo_path).expanduser().exists()

        return shutil.which(self._fallback_binary) is not None

    def execute(self, params: dict[str, Any] | None = None) -> dict[str, Any]:
        params = params or {}

        if self.is_airgapped:
            self.logger.info("Returning fixture response for tactical airgapped execution.")
            return {
                "integration_id": self.integration_id,
                "domain": self.domain,
                "mode": self.mode,
                "source": "fixture",
                "data": self._read_fixture("sample_response.json"),
                "params": params,
            }

        repository_path = self._env(self._repo_env_var)
        available = self.validate_availability()
        return {
            "integration_id": self.integration_id,
            "domain": self.domain,
            "mode": self.mode,
            "source": "local-wrapper",
            "available": available,
            "repository_path": repository_path,
            "operation": str(params.get("operation", "status")),
            "data": {
                "status": "available" if available else "unavailable",
                "note": "Configure a local repository path for offline mission deployment workflows.",
            },
        }
