"""Adapter for aureuserp personnel-readiness workflows.

Military/tactical context:
This wrapper exposes ERP personnel modules as deterministic readiness signals
for command logistics and force-generation planning in disconnected theaters.
"""

from __future__ import annotations

import logging
from pathlib import Path
import shutil
from typing import Any

import yaml

from packages.integrations.base import IntegrationAdapter, IntegrationManifest


class AureuserpAdapter(IntegrationAdapter):
    """S3M readiness adapter for aureuserp HR/personnel modules."""

    integration_id = "aureuserp"
    domain = "readiness"
    _COMMAND_CANDIDATES = ("aureuserp", "erpnext", "python3")

    def __init__(self, mode: str | None = None) -> None:
        super().__init__(mode=mode)
        self.logger = logging.getLogger("s3m.integrations.readiness.aureuserp")

    def _manifest_path(self) -> Path:
        return Path(__file__).resolve().parent / "manifest.yaml"

    @staticmethod
    def _coerce_list(value: Any) -> list[str]:
        if value is None:
            return []
        if isinstance(value, list):
            return [str(item) for item in value]
        return [str(value)]

    def _load_manifest_dict(self) -> dict[str, Any]:
        manifest_path = self._manifest_path()
        if not manifest_path.exists():
            self.logger.warning("Manifest file missing: %s", manifest_path)
            return {}
        try:
            raw = yaml.safe_load(manifest_path.read_text(encoding="utf-8")) or {}
        except yaml.YAMLError:
            self.logger.exception("Manifest YAML parsing failed: %s", manifest_path)
            return {}
        if not isinstance(raw, dict):
            self.logger.warning("Manifest is not a mapping: %s", manifest_path)
            return {}
        return raw

    def get_manifest(self) -> IntegrationManifest:
        """Load integration metadata for ERP-backed personnel readiness orchestration."""
        raw = self._load_manifest_dict()
        return IntegrationManifest(
            name=str(raw.get("name") or "aureuserp"),
            slug=str(raw.get("slug") or self.integration_id),
            domain=str(raw.get("domain") or self.domain),
            source_url=str(raw.get("source_url") or "https://github.com/aureuserp/aureuserp"),
            license=str(raw.get("license") or "Unknown"),
            description=str(
                raw.get("description")
                or "Open-source ERP integration for personnel records and readiness accounting."
            ),
            integration_type=str(raw.get("integration_type") or "adapter"),
            capabilities=self._coerce_list(
                raw.get("capabilities")
                or ["personnel_roster_sync", "hr_case_management", "readiness_finance_alignment"]
            ),
            airgapped_support=bool(raw.get("airgapped_support", True)),
        )

    def validate_availability(self) -> bool:
        """Check local aureuserp runtime availability without network dependencies."""
        if self.is_airgapped:
            return bool(self._read_fixture("sample_response.json"))

        env_prefix = self.integration_id.upper().replace("-", "_").replace(".", "_")
        configured_binary = self._env(f"{env_prefix}_BIN")
        if configured_binary and shutil.which(configured_binary):
            return True

        configured_path = self._env(f"{env_prefix}_PATH")
        if configured_path and Path(configured_path).expanduser().exists():
            return True

        return any(shutil.which(command) for command in self._COMMAND_CANDIDATES)

    def execute(self, params: dict[str, Any] | None = None) -> dict[str, Any]:
        """Execute personnel-readiness wrapper with deterministic fixture fallback."""
        request = params or {}
        if not isinstance(request, dict):
            raise TypeError("params must be a dictionary")

        operation = request.get("operation", "erp_personnel_snapshot")
        if not isinstance(operation, str) or not operation.strip() or len(operation) > 64:
            raise ValueError("operation must be a non-empty string with at most 64 characters")

        if self.is_airgapped:
            # Tactical requirement: deterministic payloads support reproducible command audits.
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
                "operation": operation,
                "error": "aureuserp runtime is not installed or configured",
                "fallback": self._read_fixture("sample_response.json"),
            }

        return {
            "integration_id": self.integration_id,
            "domain": self.domain,
            "mode": self.mode,
            "status": "ready",
            "source": "local-runtime",
            "operation": operation,
            "request": request,
            "note": "Local readiness tooling detected; external API calls remain disabled by policy.",
        }
