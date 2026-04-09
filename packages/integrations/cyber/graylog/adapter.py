"""Graylog integration adapter for S3M cyber defense operations.

Military/tactical context:
The adapter exposes log triage summaries used by tactical SOC teams to detect
distributed attacks against mission networks while operating in airgapped mode.
"""

from __future__ import annotations

from pathlib import Path
import shutil
from typing import Any

import yaml

from packages.integrations.base import IntegrationAdapter, IntegrationManifest


class GraylogAdapter(IntegrationAdapter):
    """Wrap Graylog workflows with deterministic fixture fallback."""

    integration_id = "graylog"
    domain = "cyber"
    _SUPPORTED_OPERATIONS = {"search_logs", "stream_health", "threat_summary"}

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
            name=str(raw.get("name") or "graylog"),
            slug=str(raw.get("slug") or self.integration_id),
            domain=str(raw.get("domain") or self.domain),
            source_url=str(raw.get("source_url") or ""),
            license=str(raw.get("license") or "Unknown"),
            description="Open-source log management adapter for tactical cyber monitoring.",
            integration_type="adapter",
            capabilities=["log-search", "stream-analysis", "soc-triage"],
            system_dependencies=["graylog-server", "graylogctl"],
            airgapped_support=True,
        )

    def validate_availability(self) -> bool:
        if self.is_airgapped:
            return bool(self._read_fixture("sample_response.json"))
        return any(shutil.which(command) for command in ("graylog-server", "graylogctl"))

    def execute(self, params: dict[str, Any] | None = None) -> dict[str, Any]:
        """Execute Graylog operation with strict input checks."""
        if params is not None and not isinstance(params, dict):
            raise ValueError("params must be a dictionary when provided")

        request = params or {}
        operation = str(request.get("operation", "threat_summary")).strip().lower()
        if operation not in self._SUPPORTED_OPERATIONS:
            raise ValueError(f"Unsupported operation '{operation}' for {self.integration_id}")

        if self.is_airgapped:
            self.logger.info("Returning fixture-based Graylog summary for mission SOC workflow.")
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
                "detail": "Live Graylog endpoint calls are disabled by sovereign policy in this wrapper.",
            },
        }
