"""Adapter for the soc-cert-dashboard repository.

Military/tactical context:
This wrapper supports combined SOC-CERT defense coordination for high-tempo
cyber incidents where teams need reproducible offline decision support.
"""

from __future__ import annotations

from pathlib import Path
import shutil
from typing import Any

import yaml

from packages.integrations.base import IntegrationAdapter, IntegrationManifest


class SocCertDashboardAdapter(IntegrationAdapter):
    """S3M integration adapter for soc-cert-dashboard."""

    integration_id = "soc-cert-dashboard"
    domain = "cyber"
    _COMMAND_CANDIDATES = ("soc-cert-dashboard", "soc-cert", "soccert-dashboard")

    def _manifest_path(self) -> Path:
        return Path(__file__).resolve().parent / "manifest.yaml"

    def _load_manifest_dict(self) -> dict[str, Any]:
        manifest_path = self._manifest_path()
        if not manifest_path.exists():
            self.logger.warning("Manifest file missing: %s", manifest_path)
            return {}
        try:
            data = yaml.safe_load(manifest_path.read_text(encoding="utf-8")) or {}
        except yaml.YAMLError:
            self.logger.exception("Manifest YAML parsing failed: %s", manifest_path)
            return {}
        if not isinstance(data, dict):
            self.logger.warning("Manifest is not a mapping: %s", manifest_path)
            return {}
        return data

    def get_manifest(self) -> IntegrationManifest:
        """Return local manifest metadata for orchestrator discovery."""
        raw = self._load_manifest_dict()
        return IntegrationManifest(
            name=str(raw.get("name", "soc-cert-dashboard")),
            slug=str(raw.get("slug", self.integration_id)),
            domain=str(raw.get("domain", self.domain)),
            source_url=str(raw.get("source_url", "")),
            license=str(raw.get("license", "Unknown")),
            description=str(
                raw.get(
                    "description",
                    "SOC-CERT dashboard for threat analysis and coordinated cyber response.",
                )
            ),
            integration_type=str(raw.get("integration_type", "adapter")),
            capabilities=list(raw.get("capabilities", ["soc-cert-ops", "threat-analysis", "case-correlation"])),
            airgapped_support=bool(raw.get("airgapped_support", True)),
        )

    def validate_availability(self) -> bool:
        """Validate local tool readiness for SOC-CERT operations."""
        if self.is_airgapped:
            return bool(self._read_fixture("sample_response.json"))

        env_prefix = self.integration_id.upper().replace("-", "_")
        configured_binary = self._env(f"{env_prefix}_BIN")
        if configured_binary and shutil.which(configured_binary):
            return True

        configured_path = self._env(f"{env_prefix}_PATH")
        if configured_path and Path(configured_path).exists():
            return True

        return any(shutil.which(cmd) for cmd in self._COMMAND_CANDIDATES)

    def execute(self, params: dict[str, Any] | None = None) -> dict[str, Any]:
        """Execute SOC-CERT workflow wrapper with airgapped fallback support."""
        request_params = params or {}
        if self.is_airgapped:
            self.logger.info("Airgapped mode active; returning fixture for SOC-CERT battle rhythm.")
            return {
                "integration_id": self.integration_id,
                "domain": self.domain,
                "mode": self.mode,
                "source": "fixture",
                "result": self._read_fixture("sample_response.json"),
                "request": request_params,
            }

        if not self.validate_availability():
            return {
                "integration_id": self.integration_id,
                "domain": self.domain,
                "mode": self.mode,
                "status": "unavailable",
                "error": "soc-cert-dashboard is not installed or configured",
                "request": request_params,
            }

        operation = str(request_params.get("operation", "status"))
        return {
            "integration_id": self.integration_id,
            "domain": self.domain,
            "mode": self.mode,
            "status": "ready",
            "operation": operation,
            "request": request_params,
            "note": "Local adapter validated; live SOC-CERT execution remains under mission orchestrator control.",
        }
