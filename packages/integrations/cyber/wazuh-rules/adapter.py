"""Wazuh-Rules integration adapter for cyber defense operations.

Military/tactical context:
This adapter gives S3M operators a controlled interface to Wazuh-Rules data so
SOC teams can rehearse defensive workflows without exposing mission networks
to external dependencies.
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import Any

import yaml

from packages.integrations.base import IntegrationAdapter, IntegrationManifest


class WazuhRulesAdapter(IntegrationAdapter):
    """Wrapper for Wazuh-Rules with airgapped mission support."""

    integration_id = "wazuh-rules"
    domain = "cyber"

    def _manifest_path(self) -> Path:
        return Path(__file__).resolve().parent / "manifest.yaml"

    @staticmethod
    def _coerce_str_list(value: Any) -> list[str]:
        if value is None:
            return []
        if isinstance(value, list):
            return [str(item) for item in value]
        return [str(value)]

    @staticmethod
    def _sanitize_params(params: dict[str, Any] | None) -> dict[str, Any]:
        """Validate params to prevent unsafe payload handling in mission systems."""
        if params is None:
            return {}
        if not isinstance(params, dict):
            raise ValueError("params must be a dictionary")
        if len(params) > 128:
            raise ValueError("params contains too many top-level fields")
        if any(not isinstance(key, str) for key in params):
            raise ValueError("params keys must be strings")

        # Tactical safety: normalize to JSON-safe payloads before processing.
        try:
            normalized = json.loads(json.dumps(params))
        except (TypeError, ValueError) as exc:
            raise ValueError("params must be JSON-serializable") from exc

        if len(json.dumps(normalized)) > 20000:
            raise ValueError("params payload is too large")
        return normalized

    def get_manifest(self) -> IntegrationManifest:
        raw = yaml.safe_load(self._manifest_path().read_text(encoding="utf-8")) or {}
        if not isinstance(raw, dict):
            raw = {}

        return IntegrationManifest(
            name=str(raw.get("name") or "Wazuh-Rules"),
            slug=str(raw.get("slug") or self.integration_id),
            domain=str(raw.get("domain") or self.domain),
            source_url=str(raw.get("source_url") or "https://github.com/socfortress/Wazuh-Rules"),
            license=str(raw.get("license") or "Unknown"),
            description=str(raw.get("description") or "Advanced, enriched Wazuh rules for more accurate threat detection including Suricata-correlated events."),
            integration_type=str(raw.get("integration_type") or "adapter"),
            capabilities=self._coerce_str_list(raw.get("capabilities") or ['rule_enrichment', 'alert_tuning', 'suricata_alignment', 'threat_detection']),
            pip_dependencies=self._coerce_str_list(raw.get("pip_dependencies")),
            system_dependencies=self._coerce_str_list(raw.get("system_dependencies")),
            docker_dependencies=self._coerce_str_list(raw.get("docker_dependencies")),
            airgapped_support=bool(raw.get("airgapped_support", True)),
            vendor_path=str(raw.get("vendor_path") or ""),
        )

    def validate_availability(self) -> bool:
        """Check local availability for disconnected defensive operations."""
        configured_path = self._env("WAZUH_RULES_PATH")
        if configured_path and Path(configured_path).exists():
            return True
        default_paths = (
            Path("/var/ossec/ruleset/rules"),
            Path("/var/ossec/etc/rules"),
            Path("/etc/ossec/rules"),
        )
        if any(path.exists() for path in default_paths):
            return True
        return shutil.which("wazuh-control") is not None

    def execute(self, params: dict[str, Any] | None = None) -> dict[str, Any]:
        """Execute primary workflow using fixtures when operating airgapped."""
        safe_params = self._sanitize_params(params)

        if self.is_airgapped:
            return {
                "integration_id": self.integration_id,
                "domain": self.domain,
                "mode": self.mode,
                "source": "fixture",
                "request": safe_params,
                "data": self._read_fixture("sample_response.json"),
            }

        available = self.validate_availability()
        if not available:
            return {
                "integration_id": self.integration_id,
                "domain": self.domain,
                "mode": self.mode,
                "source": "live",
                "available": False,
                "status": "unavailable",
                "message": "Local dependency check failed; set deployment path environment variables.",
                "request": safe_params,
            }

        return {
            "integration_id": self.integration_id,
            "domain": self.domain,
            "mode": self.mode,
            "source": "live",
            "available": True,
            "status": "ready",
            "message": "Wazuh rule deployment paths are available for local detection engineering.",
            "request": safe_params,
        }
