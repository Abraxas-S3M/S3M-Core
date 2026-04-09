"""OpenSearch project integration adapter for cyber analytics.

Military/tactical context:
This adapter encapsulates OpenSearch analytics summaries so operators can track
threat telemetry from contested network zones without external dependencies.
"""

from __future__ import annotations

from pathlib import Path
import shutil
from typing import Any

import yaml

from packages.integrations.base import IntegrationAdapter, IntegrationManifest


class OpensearchProjectAdapter(IntegrationAdapter):
    """Wrap OpenSearch workflows with sovereign-safe execution semantics."""

    integration_id = "opensearch-project"
    domain = "cyber"
    _SUPPORTED_OPERATIONS = {"index_health", "search_analytics", "threat_hunting"}

    def _manifest_path(self) -> Path:
        return Path(__file__).resolve().parent / "manifest.yaml"

    def _manifest_data(self) -> dict[str, Any]:
        manifest_path = self._manifest_path()
        if not manifest_path.exists():
            return {}
        loaded = yaml.safe_load(manifest_path.read_text(encoding="utf-8")) or {}
        return loaded if isinstance(loaded, dict) else {}

    def get_manifest(self) -> IntegrationManifest:
        raw = self._manifest_data()
        return IntegrationManifest(
            name=str(raw.get("name") or "opensearch-project"),
            slug=str(raw.get("slug") or self.integration_id),
            domain=str(raw.get("domain") or self.domain),
            source_url=str(raw.get("source_url") or ""),
            license=str(raw.get("license") or "Unknown"),
            description="Search and analytics adapter for tactical cyber telemetry stores.",
            integration_type="adapter",
            capabilities=["index-management", "search", "threat-hunting"],
            system_dependencies=["opensearch", "opensearch-dashboards"],
            airgapped_support=True,
        )

    def validate_availability(self) -> bool:
        if self.is_airgapped:
            return bool(self._read_fixture("sample_response.json"))
        return any(shutil.which(command) for command in ("opensearch", "opensearch-dashboards", "opensearch-plugin"))

    def execute(self, params: dict[str, Any] | None = None) -> dict[str, Any]:
        """Execute OpenSearch operation while preserving deterministic behavior."""
        if params is not None and not isinstance(params, dict):
            raise ValueError("params must be a dictionary when provided")

        request = params or {}
        operation = str(request.get("operation", "search_analytics")).strip().lower()
        if operation not in self._SUPPORTED_OPERATIONS:
            raise ValueError(f"Unsupported operation '{operation}' for {self.integration_id}")

        if self.is_airgapped:
            self.logger.info("Returning OpenSearch fixture payload for mission intelligence sync.")
            return {
                "integration_id": self.integration_id,
                "domain": self.domain,
                "mode": self.mode,
                "operation": operation,
                "source": "fixture",
                "result": self._read_fixture("sample_response.json"),
            }

        return {
            "integration_id": self.integration_id,
            "domain": self.domain,
            "mode": self.mode,
            "operation": operation,
            "source": "runtime",
            "available": self.validate_availability(),
            "result": {
                "status": "simulated",
                "detail": "Network-backed OpenSearch queries are intentionally not executed in this wrapper.",
            },
        }
