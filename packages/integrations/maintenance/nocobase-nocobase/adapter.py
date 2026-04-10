"""NocoBase integration adapter for maintenance dashboard orchestration.

Military/tactical context:
This wrapper allows sustainment teams to stage custom maintenance dashboards
locally, giving commanders a common operating picture for asset health and
repair throughput even in disconnected theaters.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
import shutil
from typing import Any

import yaml

from packages.integrations.base import IntegrationAdapter, IntegrationManifest


class NocobasenocobaseAdapter(IntegrationAdapter):
    """S3M wrapper for nocobase/nocobase maintenance dashboard workflows."""

    integration_id = "nocobase-nocobase"
    domain = "maintenance"
    _SUPPORTED_OPERATIONS = {"status", "asset_dashboard", "maintenance_kpis"}
    _COMMAND_CANDIDATES = ("nocobase", "node")

    def __init__(self, mode: str | None = None) -> None:
        super().__init__(mode=mode)
        self.logger = logging.getLogger("s3m.integrations.maintenance.nocobase-nocobase")

    def _manifest_path(self) -> Path:
        return Path(__file__).resolve().parent / "manifest.yaml"

    def _manifest_data(self) -> dict[str, Any]:
        manifest_path = self._manifest_path()
        if not manifest_path.exists():
            return {}
        loaded = yaml.safe_load(manifest_path.read_text(encoding="utf-8")) or {}
        return loaded if isinstance(loaded, dict) else {}

    @staticmethod
    def _coerce_str_list(value: Any) -> list[str]:
        if value is None:
            return []
        if isinstance(value, list):
            return [str(item) for item in value]
        return [str(value)]

    @staticmethod
    def _sanitize_params(params: dict[str, Any] | None) -> dict[str, Any]:
        """Validate dashboard request payloads before processing."""
        if params is None:
            return {}
        if not isinstance(params, dict):
            raise ValueError("params must be a dictionary")
        if any(not isinstance(key, str) for key in params):
            raise ValueError("params keys must be strings")

        # Tactical safety: deterministic JSON normalization supports audit replay.
        try:
            normalized = json.loads(json.dumps(params))
        except (TypeError, ValueError) as exc:
            raise ValueError("params must be JSON-serializable") from exc

        if len(json.dumps(normalized)) > 20000:
            raise ValueError("params payload is too large")
        return normalized

    def get_manifest(self) -> IntegrationManifest:
        """Load NocoBase metadata for mission integration cataloging."""
        raw = self._manifest_data()
        return IntegrationManifest(
            name=str(raw.get("name") or "nocobase/nocobase"),
            slug=str(raw.get("slug") or self.integration_id),
            domain=str(raw.get("domain") or self.domain),
            source_url=str(raw.get("source_url") or "https://github.com/nocobase/nocobase"),
            license=str(raw.get("license") or "Unknown"),
            description=str(
                raw.get("description")
                or "No-code/low-code platform for custom asset management dashboards."
            ),
            integration_type=str(raw.get("integration_type") or "adapter"),
            capabilities=self._coerce_str_list(
                raw.get("capabilities")
                or ["maintenance_dashboarding", "asset_workflow_composition", "kpi_reporting"]
            ),
            pip_dependencies=self._coerce_str_list(raw.get("pip_dependencies")),
            system_dependencies=self._coerce_str_list(raw.get("system_dependencies")),
            docker_dependencies=self._coerce_str_list(raw.get("docker_dependencies")),
            airgapped_support=bool(raw.get("airgapped_support", True)),
            vendor_path=str(raw.get("vendor_path") or ""),
        )

    def validate_availability(self) -> bool:
        """Check if NocoBase-compatible local runtime is available."""
        if self.is_airgapped:
            return bool(self._read_fixture("sample_response.json"))

        command_available = any(shutil.which(command) is not None for command in self._COMMAND_CANDIDATES)
        deployment_hint = bool(self._env("NOCOBASE_HOME"))
        return command_available or deployment_hint

    def execute(self, params: dict[str, Any] | None = None) -> dict[str, Any]:
        """Execute local dashboard workflow with airgapped fixture fallback."""
        safe_params = self._sanitize_params(params)
        operation = str(safe_params.get("operation") or "status").strip().lower()
        if operation not in self._SUPPORTED_OPERATIONS:
            raise ValueError(f"Unsupported operation '{operation}' for {self.integration_id}")

        if self.is_airgapped:
            self.logger.info("Returning fixture for tactical NocoBase operation=%s", operation)
            return {
                "integration_id": self.integration_id,
                "domain": self.domain,
                "mode": self.mode,
                "source": "fixture",
                "status": "ok",
                "operation": operation,
                "request": safe_params,
                "result": self._read_fixture("sample_response.json"),
            }

        if not self.validate_availability():
            return {
                "integration_id": self.integration_id,
                "domain": self.domain,
                "mode": self.mode,
                "source": "runtime",
                "status": "unavailable",
                "operation": operation,
                "request": safe_params,
                "message": "NocoBase runtime was not detected on this sovereign maintenance node.",
            }

        return {
            "integration_id": self.integration_id,
            "domain": self.domain,
            "mode": self.mode,
            "source": "runtime",
            "status": "ready",
            "operation": operation,
            "request": safe_params,
            "message": "NocoBase adapter is ready for local maintenance dashboard workflow handoff.",
        }
