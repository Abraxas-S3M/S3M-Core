"""Supply chain management dashboard integration adapter.

Military/tactical context:
This adapter stages inventory and logistics snapshots that sustain operational
readiness planning for distributed units in low-connectivity theaters.
"""

from __future__ import annotations

import logging
from pathlib import Path
import shutil
from typing import Any

import yaml

from packages.integrations.base import IntegrationAdapter, IntegrationManifest


class SupplyChainManagementDashboardAdapter(IntegrationAdapter):
    """Adapter wrapper for supply-chain management dashboard integration."""

    integration_id = "supply-chain-management-dashboard"
    domain = "dashboard"

    def __init__(self, mode: str | None = None) -> None:
        super().__init__(mode=mode)
        self.logger = logging.getLogger(
            "s3m.integrations.dashboard.supply-chain-management-dashboard"
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
        """Return integration manifest metadata for logistics workflows."""
        raw = self._manifest_dict()
        return IntegrationManifest(
            name=str(raw.get("name") or "Supply-Chain-Management-Dashboard"),
            slug=str(raw.get("slug") or self.integration_id),
            domain=str(raw.get("domain") or self.domain),
            source_url=str(
                raw.get("source_url")
                or "https://github.com/GirishKumarV25/Supply-Chain-Management-Dashboard"
            ),
            license=str(raw.get("license") or "MIT"),
            description=str(
                raw.get("description")
                or "Dashboard for inventory, suppliers, demand, and logistics visuals."
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
        """Check local tool readiness for supply chain dashboard execution."""
        fixture_ready = bool(self._read_fixture("sample_response.json"))
        command_ready = any(
            shutil.which(command) for command in ("python3", "streamlit", "node")
        )
        return fixture_ready if self.is_airgapped else command_ready

    def execute(self, params: dict[str, Any] | None = None) -> dict[str, Any]:
        """Execute adapter with secure fixture fallback in airgapped mode."""
        if params is not None and not isinstance(params, dict):
            raise ValueError("Supply-Chain-Management-Dashboard execute params must be a dictionary.")
        safe_params = params or {}
        operation = str(safe_params.get("operation") or "logistics-overview")

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
                "error": "Supply chain management dashboard runtime is unavailable.",
            }

        # Sovereign policy: keep adapter execution local and non-networked.
        return {
            "integration_id": self.integration_id,
            "domain": self.domain,
            "mode": self.mode,
            "operation": operation,
            "status": "ready",
            "message": "Local runtime validated; remote dashboard invocation is disabled by policy.",
        }
