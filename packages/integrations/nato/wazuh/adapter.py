"""Adapter for the Wazuh XDR/SIEM platform.

Military/tactical context:
This wrapper standardizes endpoint and network telemetry posture checks used in
coalition cyber defense planning on sovereign S3M nodes.
"""

from __future__ import annotations

import json
import logging
import shutil
from pathlib import Path
from typing import Any

import yaml

from packages.integrations.base import IntegrationAdapter, IntegrationManifest


class WazuhAdapter(IntegrationAdapter):
    """S3M NATO adapter for Wazuh monitoring and triage workflows."""

    integration_id = "wazuh"
    domain = "nato"
    _COMMAND_CANDIDATES = ("wazuh-control", "wazuh-agentd", "ossec-control")

    def __init__(self, mode: str | None = None) -> None:
        super().__init__(mode=mode)
        # Tactical requirement: fixed logger namespace for mission audit replay.
        self.logger = logging.getLogger("s3m.integrations.nato.wazuh")

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

    @staticmethod
    def _coerce_list(value: Any) -> list[str]:
        if value is None:
            return []
        if isinstance(value, list):
            return [str(item) for item in value]
        return [str(value)]

    @staticmethod
    def _sanitize_params(params: dict[str, Any] | None) -> dict[str, Any]:
        """Validate untrusted payloads before defensive telemetry processing."""
        if params is None:
            return {}
        if not isinstance(params, dict):
            raise ValueError("params must be a dictionary")
        if any(not isinstance(key, str) for key in params):
            raise ValueError("params keys must be strings")
        if len(params) > 128:
            raise ValueError("params contains too many top-level fields")
        payload = json.loads(json.dumps(params))
        if len(json.dumps(payload)) > 20000:
            raise ValueError("params payload is too large")
        return payload

    def get_manifest(self) -> IntegrationManifest:
        """Return metadata from local manifest for NATO-domain discovery."""
        raw = self._load_manifest_dict()
        return IntegrationManifest(
            name=str(raw.get("name") or "Wazuh"),
            slug=str(raw.get("slug") or self.integration_id),
            domain=str(raw.get("domain") or self.domain),
            source_url=str(raw.get("source_url") or "https://github.com/wazuh/wazuh"),
            license=str(raw.get("license") or "GPL-2.0"),
            description=str(
                raw.get("description")
                or "XDR/SIEM stack with host intrusion detection and vulnerability monitoring."
            ),
            integration_type=str(raw.get("integration_type") or "adapter"),
            capabilities=self._coerce_list(
                raw.get("capabilities")
                or ["xdr_monitoring", "siem_correlation", "host_intrusion_detection"]
            ),
            airgapped_support=bool(raw.get("airgapped_support", True)),
        )

    def validate_availability(self) -> bool:
        """Check local Wazuh runtime presence without remote API calls."""
        if self.is_airgapped:
            return bool(self._read_fixture("sample_response.json"))

        env_prefix = self.integration_id.upper().replace("-", "_").replace(".", "_")
        configured_binary = self._env(f"{env_prefix}_BIN")
        if configured_binary and shutil.which(configured_binary):
            return True

        configured_path = self._env(f"{env_prefix}_PATH")
        if configured_path and Path(configured_path).exists():
            return True

        return any(shutil.which(command) for command in self._COMMAND_CANDIDATES)

    def execute(self, params: dict[str, Any] | None = None) -> dict[str, Any]:
        """Wrap SIEM workflow and return fixture payloads in airgapped mode."""
        request = self._sanitize_params(params)
        operation = str(request.get("operation") or "correlate_alerts").strip().lower()
        if not operation or len(operation) > 64:
            raise ValueError("operation must be a non-empty string with at most 64 characters")

        if self.is_airgapped:
            self.logger.info("Airgapped mode active; returning Wazuh fixture for tactical cyber drill.")
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
                "error": "wazuh is not installed or configured",
                "request": request,
            }

        return {
            "integration_id": self.integration_id,
            "domain": self.domain,
            "mode": self.mode,
            "source": "local-runtime",
            "status": "ready",
            "operation": operation,
            "request": request,
            "note": "Local Wazuh dependencies validated; active response execution remains policy-gated.",
        }
