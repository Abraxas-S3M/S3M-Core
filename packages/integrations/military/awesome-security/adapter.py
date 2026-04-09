"""Adapter for awesome-security defensive tooling references.

Military/tactical context:
This wrapper helps mission cyber teams stage local vulnerability and detection
workflows (for example Snort and Wazuh) in sovereign, disconnected operations.
"""

from __future__ import annotations

from pathlib import Path
import shutil
from typing import Any

import yaml

from packages.integrations.base import IntegrationAdapter, IntegrationManifest


class AwesomeSecurityAdapter(IntegrationAdapter):
    """S3M adapter for awesome-security curated cyber toolchains."""

    integration_id = "awesome-security"
    domain = "military"
    _COMMAND_CANDIDATES = ("snort", "suricata", "wazuh-agentd", "nmap")
    _PATH_CANDIDATES = (Path("/etc/snort/snort.conf"), Path("/var/ossec/etc/ossec.conf"))

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
        """Return manifest metadata for tactical cyber tooling discovery."""
        raw = self._load_manifest_dict()
        return IntegrationManifest(
            name=str(raw.get("name", "awesome-security")),
            slug=str(raw.get("slug", self.integration_id)),
            domain=str(raw.get("domain", self.domain)),
            source_url=str(raw.get("source_url", "")),
            license=str(raw.get("license", "Unknown")),
            description=str(
                raw.get(
                    "description",
                    "Curated security tooling references for vulnerability and intrusion detection workflows.",
                )
            ),
            integration_type=str(raw.get("integration_type", "adapter")),
            capabilities=[
                str(item)
                for item in raw.get("capabilities", ["vulnerability_detection", "ids_workflows", "tool_discovery"])
            ],
            airgapped_support=bool(raw.get("airgapped_support", True)),
        )

    def validate_availability(self) -> bool:
        """Validate local security tool presence for mission cyber posture checks."""
        if self.is_airgapped:
            return bool(self._read_fixture("sample_response.json"))

        env_prefix = self.integration_id.upper().replace("-", "_")
        configured_binary = self._env(f"{env_prefix}_BIN")
        if configured_binary and shutil.which(configured_binary):
            return True

        configured_path = self._env(f"{env_prefix}_PATH")
        if configured_path and Path(configured_path).exists():
            return True

        return any(shutil.which(command) for command in self._COMMAND_CANDIDATES) or any(
            path.exists() for path in self._PATH_CANDIDATES
        )

    def execute(self, params: dict[str, Any] | None = None) -> dict[str, Any]:
        """Execute wrapper logic with deterministic fixture fallback."""
        request_params = params or {}
        if not isinstance(request_params, dict):
            raise ValueError("params must be a dictionary of tactical integration options.")

        operation = str(request_params.get("operation", "run_security_posture_check")).strip().lower()
        if self.is_airgapped:
            self.logger.info("Airgapped mode active; returning awesome-security fixture for SOC rehearsal.")
            return {
                "integration_id": self.integration_id,
                "domain": self.domain,
                "mode": self.mode,
                "status": "ok",
                "source": "fixture",
                "operation": operation,
                "request": request_params,
                "result": self._read_fixture("sample_response.json"),
            }

        if not self.validate_availability():
            return {
                "integration_id": self.integration_id,
                "domain": self.domain,
                "mode": self.mode,
                "status": "unavailable",
                "error": "awesome-security referenced tooling is not installed or configured",
                "request": request_params,
            }

        return {
            "integration_id": self.integration_id,
            "domain": self.domain,
            "mode": self.mode,
            "status": "ready",
            "operation": operation,
            "request": request_params,
            "note": "Local prerequisites validated; live security-tool orchestration is deployment-specific.",
        }
