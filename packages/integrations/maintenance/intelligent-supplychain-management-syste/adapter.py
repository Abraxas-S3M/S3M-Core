"""Adapter for Intelligent-Supplychain-Management-System.

Military/tactical context:
This wrapper supports sovereign sustainment planning by exposing deterministic
inventory and logistics risk snapshots even when command nodes are airgapped.
"""

from __future__ import annotations

import logging
from pathlib import Path
import shutil
from typing import Any

import yaml

from packages.integrations.base import IntegrationAdapter, IntegrationManifest


class IntelligentSupplychainManagementSystemAdapter(IntegrationAdapter):
    """S3M integration adapter for Intelligent-Supplychain-Management-System."""

    integration_id = "intelligent-supplychain-management-syste"
    domain = "maintenance"
    _COMMAND_CANDIDATES = ("python3", "python")

    def __init__(self, mode: str | None = None) -> None:
        super().__init__(mode=mode)
        # Tactical auditability requires a fixed logger namespace.
        self.logger = logging.getLogger("s3m.integrations.maintenance.intelligent-supplychain-management-syste")

    def _manifest_path(self) -> Path:
        return Path(__file__).resolve().parent / "manifest.yaml"

    def _load_manifest_dict(self) -> dict[str, Any]:
        manifest_path = self._manifest_path()
        if not manifest_path.exists():
            self.logger.warning("Manifest file missing: %s", manifest_path)
            return {}
        try:
            raw_manifest = yaml.safe_load(manifest_path.read_text(encoding="utf-8")) or {}
        except yaml.YAMLError:
            self.logger.exception("Manifest YAML parsing failed: %s", manifest_path)
            return {}
        if not isinstance(raw_manifest, dict):
            self.logger.warning("Manifest is not a mapping: %s", manifest_path)
            return {}
        return raw_manifest

    def get_manifest(self) -> IntegrationManifest:
        """Load metadata for sustainment orchestration and compliance checks."""
        raw = self._load_manifest_dict()
        return IntegrationManifest(
            name=str(raw.get("name") or "Intelligent-Supplychain-Management-System"),
            slug=str(raw.get("slug") or self.integration_id),
            domain=str(raw.get("domain") or self.domain),
            source_url=str(
                raw.get("source_url")
                or "https://github.com/akhil888binoy/Intelligent-Supplychain-Management-System"
            ),
            license=str(raw.get("license") or "Unknown"),
            description=str(
                raw.get("description")
                or "Blockchain-backed supply chain coordination with predictive inventory monitoring."
            ),
            integration_type=str(raw.get("integration_type") or "adapter"),
            capabilities=[
                str(item)
                for item in raw.get("capabilities")
                or ["inventory_forecasting", "supply_chain_traceability", "maintenance_resupply_alerting"]
            ],
            airgapped_support=bool(raw.get("airgapped_support", True)),
        )

    def validate_availability(self) -> bool:
        """Validate local runtime availability without external calls."""
        if self.is_airgapped:
            return bool(self._read_fixture("sample_response.json"))

        env_prefix = self.integration_id.upper().replace("-", "_")
        configured_bin = self._env(f"{env_prefix}_BIN").strip()
        if configured_bin and shutil.which(configured_bin):
            return True

        configured_path = self._env(f"{env_prefix}_PATH").strip()
        if configured_path and Path(configured_path).expanduser().exists():
            return True

        return any(shutil.which(command) for command in self._COMMAND_CANDIDATES)

    def execute(self, params: dict[str, Any] | None = None) -> dict[str, Any]:
        """Execute adapter workflow with deterministic fixture fallback."""
        request = params or {}
        if not isinstance(request, dict):
            raise TypeError("params must be a dictionary")

        operation = request.get("operation", "predict_inventory_risk")
        if not isinstance(operation, str) or not operation.strip() or len(operation) > 64:
            raise ValueError("operation must be a non-empty string with at most 64 characters")

        if self.is_airgapped:
            return {
                "integration_id": self.integration_id,
                "domain": self.domain,
                "mode": self.mode,
                "source": "fixture",
                "operation": operation,
                "request": request,
                "result": self._read_fixture("sample_response.json"),
            }

        if not self.validate_availability():
            return {
                "integration_id": self.integration_id,
                "domain": self.domain,
                "mode": self.mode,
                "status": "unavailable",
                "error": "required local tooling is not installed or configured",
                "request": request,
            }

        return {
            "integration_id": self.integration_id,
            "domain": self.domain,
            "mode": self.mode,
            "status": "ready",
            "operation": operation,
            "request": request,
            "note": "Local runtime detected; external network execution stays disabled for sovereign security.",
        }
