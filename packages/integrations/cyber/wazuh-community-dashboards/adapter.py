"""Wazuh community dashboards integration adapter.

Military/tactical context:
This adapter provides an offline-safe wrapper for SOC dashboard snapshots so
mission operators can review cyber defense posture even when disconnected.
"""

from __future__ import annotations

from pathlib import Path
import shutil
from typing import Any

import yaml

from packages.integrations.base import IntegrationAdapter, IntegrationManifest


class WazuhCommunityDashboardsAdapter(IntegrationAdapter):
    """Wrap Wazuh dashboard metadata and tactical snapshot retrieval."""

    integration_id = "wazuh-community-dashboards"
    domain = "cyber"
    _SUPPORTED_OPERATIONS = {"dashboard_summary", "threat_heatmap", "rule_hit_rate"}

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
            name=str(raw.get("name") or "Wazuh community dashboards"),
            slug=str(raw.get("slug") or self.integration_id),
            domain=str(raw.get("domain") or self.domain),
            source_url=str(raw.get("source_url") or ""),
            license=str(raw.get("license") or "Unknown"),
            description="Custom Wazuh dashboard views for tactical SOC visualization.",
            integration_type="adapter",
            capabilities=["dashboarding", "threat-visualization", "rule-analytics"],
            system_dependencies=["opensearch-dashboards", "wazuh-dashboard"],
            airgapped_support=True,
        )

    def validate_availability(self) -> bool:
        if self.is_airgapped:
            return bool(self._read_fixture("sample_response.json"))
        return any(
            shutil.which(command)
            for command in ("opensearch-dashboards", "wazuh-dashboard", "wazuh-dashboard-plugin")
        )

    def execute(self, params: dict[str, Any] | None = None) -> dict[str, Any]:
        """Execute dashboard retrieval with deterministic offline fallback."""
        if params is not None and not isinstance(params, dict):
            raise ValueError("params must be a dictionary when provided")

        request = params or {}
        operation = str(request.get("operation", "dashboard_summary")).strip().lower()
        if operation not in self._SUPPORTED_OPERATIONS:
            raise ValueError(f"Unsupported operation '{operation}' for {self.integration_id}")

        if self.is_airgapped:
            self.logger.info("Returning fixture snapshot for tactical dashboard review.")
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
                "detail": "Runtime execution stubbed to preserve sovereign offline policy.",
            },
        }
