"""Supply chain performance dashboard integration adapter.

Military/tactical context:
This adapter captures fulfillment and profitability indicators that inform
operational sustainment risk assessments in disconnected mission environments.
"""

from __future__ import annotations

import logging
from pathlib import Path
import shutil
from typing import Any

import yaml

from packages.integrations.base import IntegrationAdapter, IntegrationManifest


class SupplyChainPerformanceDashboardAdapter(IntegrationAdapter):
    """Adapter wrapper for supply-chain performance dashboard integration."""

    integration_id = "supply-chain-performance-dashboard"
    domain = "dashboard"

    def __init__(self, mode: str | None = None) -> None:
        super().__init__(mode=mode)
        self.logger = logging.getLogger(
            "s3m.integrations.dashboard.supply-chain-performance-dashboard"
        )

    @staticmethod
    def _coerce_list(value: Any) -> list[str]:
        if value is None:
            return []
        if isinstance(value, list):
            return [str(item) for item in value]
        return [str(value)]

    def _manifest_path(self) -> Path:
        return Path(__file__).resolve().parent / "manifest.yaml"

    def _manifest_dict(self) -> dict[str, Any]:
        raw = yaml.safe_load(self._manifest_path().read_text(encoding="utf-8")) or {}
        if not isinstance(raw, dict):
            return {}
        return raw

    def get_manifest(self) -> IntegrationManifest:
        """Load performance dashboard manifest for integration registry."""
        raw = self._manifest_dict()
        return IntegrationManifest(
            name=str(raw.get("name") or "Supply-Chain-Performance-Dashboard"),
            slug=str(raw.get("slug") or self.integration_id),
            domain=str(raw.get("domain") or self.domain),
            source_url=str(
                raw.get("source_url")
                or "https://github.com/PolinaBurova/Supply-Chain-Performance-Dashboard"
            ),
            license=str(raw.get("license") or "MIT"),
            description=str(
                raw.get("description")
                or "Interactive dashboard for risks, sales, fulfillment, and profitability."
            ),
            integration_type=str(raw.get("integration_type") or "adapter"),
            capabilities=self._coerce_list(raw.get("capabilities")),
            pip_dependencies=self._coerce_list(raw.get("pip_dependencies")),
            system_dependencies=self._coerce_list(raw.get("system_dependencies")),
            docker_dependencies=self._coerce_list(raw.get("docker_dependencies")),
            airgapped_support=bool(raw.get("airgapped_support", True)),
            vendor_path=str(raw.get("vendor_path") or ""),
        )

    def validate_availability(self) -> bool:
        """Check runtime/tool readiness for performance dashboard operations."""
        fixture_ready = bool(self._read_fixture("sample_response.json"))
        command_ready = any(
            shutil.which(command) for command in ("python3", "streamlit", "node")
        )
        return fixture_ready if self.is_airgapped else command_ready

    def execute(self, params: dict[str, Any] | None = None) -> dict[str, Any]:
        """Execute wrapper and return fixture-backed response when airgapped."""
        safe_params = params or {}
        operation = str(safe_params.get("operation") or "performance-overview")

        if self.is_airgapped:
            return {
                "integration_id": self.integration_id,
                "domain": self.domain,
                "mode": self.mode,
                "operation": operation,
                "source": "fixture",
                "data": self._read_fixture("sample_response.json"),
            }

        if not self.validate_availability():
            return {
                "integration_id": self.integration_id,
                "domain": self.domain,
                "mode": self.mode,
                "operation": operation,
                "status": "unavailable",
                "error": "Supply chain performance dashboard runtime is unavailable.",
            }

        # External execution is intentionally blocked for sovereign deployments.
        return {
            "integration_id": self.integration_id,
            "domain": self.domain,
            "mode": self.mode,
            "operation": operation,
            "status": "ready",
            "message": "Local runtime validated; remote dashboard invocation is disabled by policy.",
        }
